"""knowns 출처(provenance) 추적.

모든 known 값이 "어느 문장에서 왔는지"를 재구성하고, 물리 설정과 무관한
배경 문장에서 추출된 값을 식별한다.

왜 필요한가: 배경 문장의 수치("시험 시간 60 초", "저울의 질량 2 kg 추")가
knowns로 주입되면, 그 값으로 계산한 답은 그 값을 넣은 방정식과 '일관'되므로
역대입 잔차가 원리상 잡지 못한다 (garbage-in, consistent-out).
출처 검증이 이 클래스의 유일한 방어선이다.

분류 정책은 보수적으로: background 판정은 강한 마커가 있을 때만.
무고 오탐 0은 하니스(routing_confusion_report --provenance 섹션)로 상시 측정.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.models import CanonicalProblem
from engine.extraction.normalizer import normalize

# 기본값/문구 유도 등 사용자 텍스트에서 오지 않은 값의 source_text 센티널
_TRUSTED_SOURCE_MARKERS = (
    "기본값",
    "horizontal_phrase",
    "vertical_phrase",
    "explicit_angle",
    "정지 상태에서 출발",
    "멈춤/최종 정지",
)

# background 판정 마커 — 물리 설정이 아닌 서술임을 강하게 시사하는 표현만.
# (보수적으로 유지할 것: 여기 넣는 단어 하나가 무고 오탐을 만든다.)
_BACKGROUND_MARKERS = (
    "참고로",
    "온도", "기온", "섭씨", "화씨", "체온",
    "카메라", "관찰자", "기록지", "칠판", "교과서", "시험지",
    "저울", "자로 재",
    "옆 반", "선생", "친구",
    "무관하", "무관한", "관계없", "상관없",
    "사용하지 않", "쓰지 않",
    "날씨", "습도",
    "시험 시간", "제한 시간", "쉬는 시간",
)

_QUESTION_MARKERS = ("구하라", "구하시오", "구하여라", "계산하라", "계산하시오", "얼마", "?")

_PHYSICS_MARKERS = (
    "질량", "속도", "속력", "가속도", "힘", "마찰", "경사", "빗면", "사면",
    "던졌", "던진", "발사", "떨어", "낙하", "충돌", "도르래", "매달",
    "스프링", "용수철", "진동", "에너지", "한 일", "충격량", "토크",
    "회전", "각속도", "반지름", "커브", "곡선", "정지 상태", "등가속",
    "kg", "m/s", "N", "rad",
)


@dataclass
class Sentence:
    index: int
    start: int
    end: int
    text: str
    relevance: str  # "question" | "background" | "physics" | "neutral"
    reasons: list[str] = field(default_factory=list)


@dataclass
class KnownProvenance:
    symbol: str
    value: float | None
    unit: str | None
    snippet: str | None
    sentence: Sentence | None
    origin: str  # "text" | "trusted" | "unlocated" | "ambiguous"

    @property
    def suspicious(self) -> bool:
        """확실히 배경 문장 유래 — suite에서 사용 심볼이면 답 보류."""
        return self.origin == "text" and self.sentence is not None and self.sentence.relevance == "background"

    @property
    def ambiguous(self) -> bool:
        """동일 스니펫이 물리·배경 문장에 모두 출현 — 항상 warning-tier."""
        return self.origin == "ambiguous"


@dataclass
class ProvenanceReport:
    sentences: list[Sentence]
    entries: list[KnownProvenance]

    @property
    def suspicious_entries(self) -> list[KnownProvenance]:
        return [e for e in self.entries if e.suspicious]

    @property
    def ambiguous_entries(self) -> list[KnownProvenance]:
        return [e for e in self.entries if e.ambiguous]


def split_sentences(text: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    start = 0
    for m in re.finditer(r"[.!?](?:\s+|$)", text):
        end = m.end()
        chunk = text[start:end].strip()
        if chunk:
            sentences.append(Sentence(len(sentences), start, end, chunk, "neutral"))
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(Sentence(len(sentences), start, len(text), tail, "neutral"))
    for s in sentences:
        s.relevance, s.reasons = _classify(s.text)
    return sentences


def _classify(sentence: str) -> tuple[str, list[str]]:
    # 우선순위: background > question > physics > neutral.
    # 배경 마커가 있으면 물리 단어가 섞여 있어도 background다 —
    # 주입 문장("저울의 질량 2 kg 추")이 물리 단어(질량)를 포함하기 때문.
    bg = [m for m in _BACKGROUND_MARKERS if m in sentence]
    if bg:
        return "background", [f"배경 마커: {', '.join(bg[:3])}"]
    if any(m in sentence for m in _QUESTION_MARKERS):
        return "question", ["질문 문장"]
    if any(m in sentence for m in _PHYSICS_MARKERS):
        return "physics", ["물리 문맥"]
    return "neutral", []


def _anchor_offset(snippet: str) -> int:
    """스니펫이 문장 경계를 넘을 수 있으므로, 값이 있는 위치(마지막 숫자)를 앵커로."""
    last = None
    for m in re.finditer(r"\d+(?:\.\d+)?", snippet):
        last = m
    return last.start() if last else max(len(snippet) - 1, 0)


def _locate(snippet: str, text: str, sentences: list[Sentence]) -> tuple[Sentence | None, bool]:
    """(primary_sentence, ambiguous). 스니펫의 모든 출현을 조사한다.
    primary는 첫 출현(추출기가 취했을 위치), ambiguous는 다른 출현 중
    배경 문장에 있는 것이 존재해 출처를 확정할 수 없는 경우."""
    offset = _anchor_offset(snippet)

    def sentence_at(pos: int) -> Sentence | None:
        for s in sentences:
            if s.start <= pos < s.end:
                return s
        return sentences[-1] if sentences else None

    positions = [m.start() for m in re.finditer(re.escape(snippet), text)]
    if not positions:
        return None, False
    primary = sentence_at(positions[0] + offset)
    if primary is None:
        return None, False
    if primary.relevance == "background":
        return primary, False
    for pos in positions[1:]:
        s = sentence_at(pos + offset)
        if s is not None and s.relevance == "background":
            return primary, True  # 물리 문장에도, 배경 문장에도 있음 → 다의적
    return primary, False


def analyze(cp: CanonicalProblem) -> ProvenanceReport:
    """knowns 각각을 출처 문장에 매핑. 스니펫은 정규화 텍스트 기준이므로 동일 기준에서 탐색."""
    text = normalize(cp.raw_text or "")
    sentences = split_sentences(text)
    entries: list[KnownProvenance] = []
    for sym, q in (cp.knowns or {}).items():
        snippet = getattr(q, "source_text", None)
        if not snippet or any(mark in snippet for mark in _TRUSTED_SOURCE_MARKERS):
            entries.append(KnownProvenance(sym, q.value, q.unit, snippet, None, "trusted"))
            continue
        sent, is_ambiguous = _locate(snippet, text, sentences)
        if sent is None:
            entries.append(KnownProvenance(sym, q.value, q.unit, snippet, None, "unlocated"))
        elif is_ambiguous:
            entries.append(KnownProvenance(sym, q.value, q.unit, snippet, sent, "ambiguous"))
        else:
            entries.append(KnownProvenance(sym, q.value, q.unit, snippet, sent, "text"))
    return ProvenanceReport(sentences, entries)
