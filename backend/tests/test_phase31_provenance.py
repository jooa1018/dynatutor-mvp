from __future__ import annotations

import pytest

from engine.extraction.extractor import extract_problem
from engine.extraction.normalizer import normalize
from engine.verification.provenance import analyze, split_sentences


def _solve(problem: str):
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem(problem)
    matches = sorted([m for s in SolverRegistry().solvers if (m := s.match(cp))], key=lambda m: -m.score)
    assert matches
    return cp, matches[0].solver.solve(cp)


# ------------------------------------------------------------ classification
@pytest.mark.unit
def test_sentence_classification_priorities():
    sents = split_sentences("질량 5 kg 물체가 움직인다. 참고로 저울의 질량 2 kg 추는 사용하지 않았다. 가속도를 구하라.")
    assert [s.relevance for s in sents] == ["physics", "background", "question"]


@pytest.mark.unit
def test_background_marker_beats_physics_keyword():
    # 주입 문장은 물리 단어(질량/힘)를 포함하므로 background가 우선이어야 한다.
    sents = split_sentences("옆 반 학생은 힘 5 N 문제를 풀고 있었다.")
    assert sents[0].relevance == "background"


# ------------------------------------------------------------ analyze
@pytest.mark.unit
def test_clean_problem_has_no_suspicious_knowns():
    cp = extract_problem("높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. 시간과 수평거리를 구하라.")
    prov = analyze(cp)
    assert not prov.suspicious_entries and not prov.ambiguous_entries
    assert any(e.origin == "trusted" for e in prov.entries)  # g 기본값 등


@pytest.mark.unit
def test_injected_known_is_flagged_with_sentence():
    cp = extract_problem("마찰 없는 30도 경사면에서 블록의 가속도를 구하라. 옆 반 학생은 힘 5 N 문제를 풀고 있었다.")
    prov = analyze(cp)
    flagged = {e.symbol: e for e in prov.suspicious_entries}
    assert "F" in flagged
    assert "학생" in flagged["F"].sentence.text


@pytest.mark.unit
def test_sentence_spanning_snippet_anchors_on_value():
    # 정규식 스니펫이 문장 경계를 넘어도 값(1 m)이 있는 배경 문장으로 귀속되어야 한다.
    cp = extract_problem("초속도 10m/s, 발사각 20도인 포물선 운동에서 같은 높이에 착지한다. 사거리는? 참고로 실험 기록지에는 높이 1 m 선반이 그려져 있다.")
    prov = analyze(cp)
    flagged = {e.symbol for e in prov.suspicious_entries} | {e.symbol for e in prov.ambiguous_entries}
    assert "h" in flagged


@pytest.mark.unit
def test_same_value_in_physics_and_background_is_ambiguous_not_error():
    cp = extract_problem("질량 2kg 물체에 알짜일 16J이 작용했다. 최종속도는? 참고로 저울의 질량 2 kg 추는 사용하지 않았다.")
    prov = analyze(cp)
    # '2 kg'가 물리·배경 문장에 모두 있으므로 확정 배경(suspicious)이 아니라 다의적이어야 한다.
    ambiguous = {e.symbol for e in prov.ambiguous_entries}
    suspicious = {e.symbol for e in prov.suspicious_entries}
    assert ambiguous and not suspicious


# ------------------------------------------------------------ suite policy
@pytest.mark.regression
def test_irrelevant_injection_keeps_answer_with_warning():
    from engine.verification.suite import verify_result

    cp, result = _solve("마찰 없는 30도 경사면에서 블록의 가속도를 구하라. 참고로 저울의 질량 2 kg 추는 사용하지 않았다.")
    rep = verify_result(cp, result)
    assert rep.passed and not rep.errors, "미사용 심볼 주입은 답을 죽이면 안 됨"
    assert any(w.startswith("출처 의심") for w in rep.warnings)


@pytest.mark.regression
def test_relevant_injection_withholds_answer_with_cause():
    from engine.verification.suite import verify_result

    # theta는 경사면 계산에 사용되는 심볼 → 배경 문장에서 오면 답 보류.
    cp, result = _solve("마찰 없는 경사면에서 블록의 가속도를 구하라. 참고로 칠판에는 각도 25도 예제가 남아 있었다.")
    rep = verify_result(cp, result)
    assert not rep.passed
    assert any(e.startswith("출처 의심") and "칠판" in e for e in rep.errors)


@pytest.mark.regression
def test_clean_solve_reports_positive_provenance_check():
    from engine.verification.suite import verify_result

    cp, result = _solve("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    rep = verify_result(cp, result)
    assert rep.passed
    assert any(c.startswith("출처:") for c in rep.checks)


@pytest.mark.regression
def test_service_withholds_on_relevant_background_injection():
    """서비스 레벨: 배경 문장 주입으로 계산이 오염되면 ok=False + 원인 문장 명시."""
    from engine.services import solve_problem

    result = solve_problem("마찰 없는 경사면에서 블록의 가속도를 구하라. 참고로 칠판에는 각도 25도 예제가 남아 있었다.")
    assert result.ok is False
    assert any("출처 의심" in e for e in result.verification.errors)
    assert result.unsupported_reason
