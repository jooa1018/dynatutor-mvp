import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("DYNATUTOR_DB", Path(__file__).resolve().parents[2] / "dynatutor_records.sqlite"))

REVIEW_INTERVALS = [1, 2, 4, 7, 14, 30, 60]


def _today() -> date:
    return date.today()


def _iso(d: date | datetime | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.replace(microsecond=0).isoformat(sep=" ")
    return d.isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_text TEXT NOT NULL,
            student_solution TEXT,
            solver TEXT,
            answer_display TEXT,
            problem_type TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            note TEXT,
            raw_result_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    _migrate(con)
    con.commit()
    return con


def _migrate(con: sqlite3.Connection) -> None:
    existing = {row[1] for row in con.execute("PRAGMA table_info(records)").fetchall()}
    columns = {
        "difficulty": "TEXT DEFAULT '미지정'",
        "favorite": "INTEGER NOT NULL DEFAULT 0",
        "review_due": "TEXT",
        "review_count": "INTEGER NOT NULL DEFAULT 0",
        "last_reviewed_at": "TEXT",
        "mastery": "INTEGER NOT NULL DEFAULT 0",
        "source": "TEXT DEFAULT 'manual'",
        "updated_at": "TEXT",
    }
    for name, ddl in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE records ADD COLUMN {name} {ddl}")
    con.execute("UPDATE records SET review_due = COALESCE(review_due, date(created_at, '+1 day'))")
    con.execute("UPDATE records SET updated_at = COALESCE(updated_at, created_at)")


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x]
    if isinstance(value, str):
        try:
            out = json.loads(value)
            if isinstance(out, list):
                return [str(x) for x in out if x]
        except Exception:
            return [value]
    return []


def add_record(payload: dict[str, Any]) -> dict[str, Any]:
    con = _connect()
    tags = _json_list(payload.get("tags"))
    review_due = payload.get("review_due") or _iso(_today() + timedelta(days=1))
    cur = con.execute(
        """
        INSERT INTO records(
            problem_text, student_solution, solver, answer_display, problem_type,
            tags_json, note, raw_result_json, difficulty, favorite, review_due,
            review_count, last_reviewed_at, mastery, source, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            payload.get("problem_text"),
            payload.get("student_solution"),
            payload.get("solver"),
            payload.get("answer_display"),
            payload.get("problem_type"),
            json.dumps(tags, ensure_ascii=False),
            payload.get("note"),
            json.dumps(payload.get("raw_result"), ensure_ascii=False) if payload.get("raw_result") is not None else None,
            payload.get("difficulty") or _difficulty_from_tags(tags),
            1 if payload.get("favorite") else 0,
            review_due,
            int(payload.get("review_count") or 0),
            payload.get("last_reviewed_at"),
            int(payload.get("mastery") or 0),
            payload.get("source") or "manual",
        ),
    )
    con.commit()
    row = con.execute("SELECT * FROM records WHERE id=?", (cur.lastrowid,)).fetchone()
    con.close()
    return _row_to_item(row)


def list_records(limit: int = 50, *, favorite: bool | None = None, due_only: bool = False, query: str | None = None) -> list[dict[str, Any]]:
    con = _connect()
    where: list[str] = []
    params: list[Any] = []
    if favorite is not None:
        where.append("favorite=?")
        params.append(1 if favorite else 0)
    if due_only:
        where.append("date(review_due) <= date('now')")
    if query:
        where.append("(problem_text LIKE ? OR note LIKE ? OR problem_type LIKE ? OR solver LIKE ?)")
        q = f"%{query}%"
        params.extend([q, q, q, q])
    sql = "SELECT * FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date(review_due) ASC, id DESC LIMIT ?"
    params.append(limit)
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [_row_to_item(r) for r in rows]


def get_record(record_id: int) -> dict[str, Any] | None:
    con = _connect()
    row = con.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    con.close()
    return _row_to_item(row) if row else None


def update_record(record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"note", "favorite", "review_due", "difficulty", "tags", "mastery", "source"}
    sets: list[str] = []
    params: list[Any] = []
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key == "tags":
            sets.append("tags_json=?")
            params.append(json.dumps(_json_list(value), ensure_ascii=False))
        elif key == "favorite":
            sets.append("favorite=?")
            params.append(1 if value else 0)
        else:
            sets.append(f"{key}=?")
            params.append(value)
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(record_id)
        con = _connect()
        con.execute(f"UPDATE records SET {', '.join(sets)} WHERE id=?", params)
        con.commit()
        row = con.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        con.close()
        return _row_to_item(row)
    item = get_record(record_id)
    if not item:
        raise KeyError(record_id)
    return item


def mark_review(record_id: int, correct: bool, note: str | None = None) -> dict[str, Any]:
    con = _connect()
    row = con.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if not row:
        con.close()
        raise KeyError(record_id)
    review_count = int(row["review_count"] or 0) + 1
    old_mastery = int(row["mastery"] or 0)
    mastery = max(0, min(6, old_mastery + (1 if correct else -1)))
    if correct:
        interval = REVIEW_INTERVALS[min(mastery, len(REVIEW_INTERVALS) - 1)]
    else:
        interval = 1
    due = _today() + timedelta(days=interval)
    merged_note = row["note"] or ""
    if note:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        merged_note = (merged_note + "\n" if merged_note else "") + f"[{stamp} 복습 {'정답' if correct else '오답'}] {note}"
    con.execute(
        """
        UPDATE records
        SET review_count=?, mastery=?, review_due=?, last_reviewed_at=datetime('now'), note=?, updated_at=datetime('now')
        WHERE id=?
        """,
        (review_count, mastery, _iso(due), merged_note, record_id),
    )
    con.commit()
    out = con.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    con.close()
    return _row_to_item(out)


def delete_record(record_id: int) -> bool:
    con = _connect()
    cur = con.execute("DELETE FROM records WHERE id=?", (record_id,))
    con.commit()
    con.close()
    return cur.rowcount > 0


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "problem_text": row["problem_text"],
        "student_solution": row["student_solution"],
        "solver": row["solver"],
        "answer_display": row["answer_display"],
        "problem_type": row["problem_type"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "note": row["note"],
        "created_at": row["created_at"],
        "difficulty": row["difficulty"] or "미지정",
        "favorite": bool(row["favorite"]),
        "review_due": row["review_due"],
        "review_count": int(row["review_count"] or 0),
        "last_reviewed_at": row["last_reviewed_at"],
        "mastery": int(row["mastery"] or 0),
        "source": row["source"] or "manual",
    }


def _row_to_export_item(row: sqlite3.Row) -> dict[str, Any]:
    item = _row_to_item(row)
    item["raw_result"] = json.loads(row["raw_result_json"] or "null")
    return item


def _difficulty_from_tags(tags: list[str]) -> str:
    for x in ["상급", "중급", "입문"]:
        if x in tags:
            return x
    if any(t in {"코리올리", "상대가속도", "평면강체", "극좌표"} for t in tags):
        return "상급"
    return "미지정"


def record_stats() -> dict[str, Any]:
    con = _connect()
    rows = con.execute("SELECT problem_type, solver, tags_json, favorite, review_due, mastery, review_count FROM records").fetchall()
    con.close()

    by_type: dict[str, int] = {}
    by_solver: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    due = 0
    favorite_count = 0
    mastery_total = 0
    for row in rows:
        ptype = row["problem_type"] or "unknown"
        solver = row["solver"] or "unknown"
        by_type[ptype] = by_type.get(ptype, 0) + 1
        by_solver[solver] = by_solver.get(solver, 0) + 1
        if row["favorite"]:
            favorite_count += 1
        mastery_total += int(row["mastery"] or 0)
        if row["review_due"] and row["review_due"] <= _iso(_today()):
            due += 1
        for tag in json.loads(row["tags_json"] or "[]"):
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    weakest = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "total": len(rows),
        "by_type": by_type,
        "by_solver": by_solver,
        "top_tags": dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]),
        "weakest_types": [{"problem_type": k, "count": v} for k, v in weakest],
        "due_today": due,
        "favorite_count": favorite_count,
        "average_mastery": round(mastery_total / len(rows), 2) if rows else 0.0,
    }


def due_records(limit: int = 10) -> list[dict[str, Any]]:
    return list_records(limit=limit, due_only=True)


def export_records() -> dict[str, Any]:
    con = _connect()
    rows = con.execute("SELECT * FROM records ORDER BY id ASC").fetchall()
    con.close()
    return {
        "format": "dynatutor-local-notebook-v1",
        "exported_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        "count": len(rows),
        "records": [_row_to_export_item(r) for r in rows],
    }


def import_records(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("records 배열이 필요합니다.")
    imported = 0
    for item in records:
        if not isinstance(item, dict) or not item.get("problem_text"):
            continue
        add_record({
            "problem_text": item.get("problem_text"),
            "student_solution": item.get("student_solution"),
            "solver": item.get("solver"),
            "answer_display": item.get("answer_display"),
            "problem_type": item.get("problem_type"),
            "tags": item.get("tags") or [],
            "note": item.get("note"),
            "raw_result": item.get("raw_result"),
            "difficulty": item.get("difficulty"),
            "favorite": item.get("favorite"),
            "review_due": item.get("review_due"),
            "review_count": item.get("review_count") or 0,
            "last_reviewed_at": item.get("last_reviewed_at"),
            "mastery": item.get("mastery") or 0,
            "source": item.get("source") or "import",
        })
        imported += 1
    return {"ok": True, "imported": imported, "total_after_import": record_stats()["total"]}
