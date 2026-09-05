"""Real SQLite cold-start migration regressions; no solver/provider doubles."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch


# Import the production storage file directly: these stdlib-only tests remain
# executable independently of unrelated optional physics/provider dependencies.
SPEC = importlib.util.spec_from_file_location(
    "notebook_under_test", Path(__file__).resolve().parents[1] / "engine/storage/notebook.py"
)
notebook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notebook)


class NotebookInitializationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "records.sqlite"
        self.path_patch = patch.object(notebook, "DB_PATH", self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def concurrent_reads(self):
        # Align both schema snapshots under the unfenced implementation. With
        # BEGIN IMMEDIATE the second connection waits instead; the short barrier
        # expires and the first transaction finishes normally. No schema fake.
        snapshots = threading.Barrier(2, timeout=0.5)
        real_connect = sqlite3.connect

        class SnapshotCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchall(self):
                rows = self.cursor.fetchall()
                try:
                    snapshots.wait()
                except threading.BrokenBarrierError:
                    pass
                return rows

        class CoordinatedConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                cursor = super().execute(sql, *args, **kwargs)
                if sql == "PRAGMA table_info(records)":
                    return SnapshotCursor(cursor)
                return cursor

        def connect(*args, **kwargs):
            return real_connect(*args, factory=CoordinatedConnection, **kwargs)

        with patch.object(notebook.sqlite3, "connect", side_effect=connect):
            with ThreadPoolExecutor(max_workers=2) as executor:
                tasks = [executor.submit(notebook.list_records), executor.submit(notebook.record_stats)]
                outcomes, errors = [], []
                for task in tasks:
                    try:
                        outcomes.append(task.result(timeout=8))
                    except Exception as error:
                        errors.append(f"{type(error).__name__}: {error}")
        self.assertEqual(errors, [], errors)
        return outcomes

    def test_simultaneous_first_reads_initialize_one_complete_schema(self):
        outcomes = self.concurrent_reads()
        self.assertEqual(outcomes[0], [])
        self.assertEqual(outcomes[1]["total"], 0)
        with sqlite3.connect(self.path) as con:
            columns = [row[1] for row in con.execute("PRAGMA table_info(records)")]
        self.assertEqual(len(columns), len(set(columns)))
        self.assertTrue({"difficulty", "source", "verified", "updated_at"} <= set(columns))

    def test_existing_legacy_data_survives_concurrent_migration(self):
        # Existing records must survive the same startup race, including the
        # fail-closed legacy provenance rule and unchanged stored receipt bytes.
        raw = json.dumps({"ok": True, "verification": {"passed": True}, "receipt": "existing"})
        with sqlite3.connect(self.path) as con:
            con.execute("""CREATE TABLE records (
                id INTEGER PRIMARY KEY, problem_text TEXT NOT NULL,
                student_solution TEXT, solver TEXT, answer_display TEXT,
                problem_type TEXT, tags_json TEXT NOT NULL DEFAULT '[]',
                note TEXT, raw_result_json TEXT, created_at TEXT DEFAULT (datetime('now')),
                source TEXT DEFAULT 'local-study')""")
            con.execute("INSERT INTO records(id,problem_text,raw_result_json) VALUES(1,?,?)", ("original problem", raw))
        self.concurrent_reads()
        exported = notebook.export_records()["records"]
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["problem_text"], "original problem")
        self.assertEqual(exported[0]["raw_result"], json.loads(raw))
        self.assertEqual(exported[0]["source"], "engine")
        self.assertTrue(exported[0]["verified"])

    def test_failed_migration_rolls_back_schema_and_closes_connection(self):
        observed = []
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            observed.append(con)
            return con

        def fail(con):
            con.execute("ALTER TABLE records ADD COLUMN partial_migration TEXT")
            raise RuntimeError("injected migration failure")

        with patch.object(notebook.sqlite3, "connect", side_effect=connect), patch.object(notebook, "_migrate", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "injected migration failure"):
                notebook._connect()
        with self.assertRaises(sqlite3.ProgrammingError):
            observed[0].execute("SELECT 1")
        with real_connect(self.path) as con:
            self.assertEqual(con.execute("SELECT name FROM sqlite_master WHERE name='records'").fetchall(), [])
        # A later genuine request can create the full schema without a restart.
        self.assertEqual(notebook.record_stats()["total"], 0)

    def test_failed_legacy_receipt_stays_unverified_after_repeated_connections(self):
        notebook.add_record({"problem_text": "manual entry", "source": "manual"})
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE records SET source='local-study', raw_result_json=?", (json.dumps({"ok": True, "verification": {"passed": False}}),))
        self.concurrent_reads()
        for _ in range(2):
            item = notebook.export_records()["records"][0]
            self.assertEqual(item["source"], "manual")
            self.assertFalse(item["verified"])
            self.assertFalse(item["raw_result"]["verification"]["passed"])


if __name__ == "__main__":
    unittest.main()
