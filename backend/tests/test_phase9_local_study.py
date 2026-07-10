from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from engine.storage import notebook


def _client(tmp_path):
    notebook.DB_PATH = tmp_path / "test_records.sqlite"
    return TestClient(app)


def test_local_notebook_review_schedule_and_stats(tmp_path):
    client = _client(tmp_path)
    payload = {
        "problem_text": "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        "solver": "incline_no_friction",
        "answer_display": "a = 4.905 m/s²",
        "problem_type": "particle_on_incline",
        "tags": ["경사면", "local-study"],
        "favorite": True,
    }
    r = client.post("/records", json=payload)
    assert r.status_code == 200
    item = r.json()
    assert item["favorite"] is True
    assert item["review_due"] == (date.today() + timedelta(days=1)).isoformat()

    reviewed = client.post(f"/records/{item['id']}/review", json={"correct": True, "note": "다시 풀었음"})
    assert reviewed.status_code == 200
    assert reviewed.json()["review_count"] == 1
    assert reviewed.json()["mastery"] == 1

    stats = client.get("/records/stats").json()
    assert stats["total"] == 1
    assert stats["favorite_count"] == 1
    assert stats["average_mastery"] == 1.0


def test_study_dashboard_and_practice_set(tmp_path):
    client = _client(tmp_path)
    client.post("/records", json={
        "problem_text": "코리올리 문제",
        "solver": "coriolis_relative_motion",
        "answer_display": "a_C = 4.8 m/s²",
        "problem_type": "coriolis_relative_motion",
        "tags": ["코리올리", "상급"],
        "review_due": date.today().isoformat(),
    })
    dashboard = client.get("/study/dashboard").json()
    assert dashboard["ok"] is True
    assert dashboard["stats"]["due_today"] >= 1
    assert dashboard["due_records"]
    assert dashboard["recommended_examples"]
    assert dashboard["daily_plan"]

    practice = client.get("/study/practice?category=개인 학습 드릴&count=3").json()
    assert practice["ok"] is True
    assert len(practice["examples"]) == 3
    assert all(e["category"] == "개인 학습 드릴" for e in practice["examples"])


def test_notebook_export_import_roundtrip(tmp_path):
    client = _client(tmp_path)
    client.post("/records", json={
        "problem_text": "정지 상태에서 출발한 물체가 가속도 2m/s²로 5초 동안 직선 운동한다. 최종속도를 구하라.",
        "solver": "constant_acceleration_1d",
        "answer_display": "v_f = 10.000 m/s",
        "problem_type": "constant_acceleration_1d",
        "tags": ["등가속도"],
    })
    exported = client.get("/records/export")
    assert exported.status_code == 200
    data = exported.json()
    assert data["format"] == "dynatutor-local-notebook-v1"
    assert data["count"] == 1

    # import appends records into local notebook; useful for personal backup restore.
    imported = client.post("/records/import", json=data)
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    assert client.get("/records/stats").json()["total"] == 2
