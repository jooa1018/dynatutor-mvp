from pydantic import BaseModel, Field


class ProblemRequest(BaseModel):
    problem_text: str = Field(..., min_length=2, description="사용자가 입력한 동역학 문제")
    student_solution: str | None = Field(None, description="학생 풀이. 없으면 빈 값")
    level: str = Field("beginner", description="설명 난이도")
    clarify_patch: dict | None = Field(None, description="되묻기 선택지 적용 patch (system_type/subtype/assume/set_known)")
    canonical_patch: dict | None = Field(None, description="앱이 이해한 조건 카드에서 수정한 canonical patch")


class FeedbackRequest(BaseModel):
    problem_text: str = Field(..., min_length=2)
    student_solution: str = Field(..., min_length=1)
    level: str = "beginner"
