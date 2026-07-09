from __future__ import annotations

from app.schemas.examples import ExampleProblemModel
from app.schemas.records import RecordItem, RecordStats
from app.schemas.study import DailyTask, PracticeSetResponse, StudyDashboardResponse
from engine.examples.library import pick_practice_examples, recommended_examples_for_types
from engine.storage.notebook import due_records, record_stats


def build_study_dashboard(limit: int = 8) -> StudyDashboardResponse:
    stats_dict = record_stats()
    stats = RecordStats(**stats_dict)
    due = [RecordItem(**r) for r in due_records(limit)]
    weak_types = [x["problem_type"] for x in stats_dict.get("weakest_types", [])]
    examples = [ExampleProblemModel(**e) for e in recommended_examples_for_types(weak_types, limit=6)]
    plan: list[DailyTask] = []
    if due:
        plan.append(DailyTask(title="오늘 복습", body=f"복습 예정 문제가 {len(due)}개 있습니다. 먼저 다시 풀어보세요.", action="review_due", priority=1))
    else:
        plan.append(DailyTask(title="새 문제 3개", body="오늘은 개인 학습 드릴에서 3문제를 골라 풀고 오답노트에 저장해보세요.", action="solve_practice", priority=2))
    if weak_types:
        plan.append(DailyTask(title="약점 유형 보강", body=f"가장 많이 저장된 약점 유형은 {weak_types[0]}입니다. 관련 예제를 다시 풀어보세요.", action="weakness_drill", priority=2))
    plan.append(DailyTask(title="풀이 습관", body="모든 문제에서 FBD → 좌표축 → 식 → 단위 검산 순서로 써보세요.", action="habit", priority=3))
    return StudyDashboardResponse(
        stats=stats,
        due_records=due,
        recommended_examples=examples,
        daily_plan=plan,
        weak_types=weak_types,
    )


def build_practice_set(category: str | None = None, difficulty: str | None = None, count: int = 6) -> PracticeSetResponse:
    examples = [ExampleProblemModel(**e) for e in pick_practice_examples(category, difficulty, count)]
    title_bits = ["개인 연습 세트"]
    if category and category != "전체":
        title_bits.append(category)
    if difficulty and difficulty != "전체":
        title_bits.append(difficulty)
    return PracticeSetResponse(title=" · ".join(title_bits), category=category, difficulty=difficulty, examples=examples)
