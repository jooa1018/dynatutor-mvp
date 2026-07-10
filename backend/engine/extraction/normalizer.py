import re

_NUM = r"(-?\d+(?:,\d{3})*(?:\.\d+)?)"


def _num_to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _fmt(x: float) -> str:
    # 너무 긴 소수 표현을 줄여서 파서가 안정적으로 읽게 한다.
    return (f"{x:.10g}")


def _convert_unit(pattern: str, text: str, factor: float, target_unit: str) -> str:
    def repl(m: re.Match) -> str:
        return f"{_fmt(_num_to_float(m.group(1)) * factor)} {target_unit}"
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def normalize(text: str) -> str:
    """Korean/English dynamics text normalization.

    한국어 교재식 표현을 solver가 다루기 쉬운 SI 중심 표현으로 정리한다.
    예: 30도 -> 30 deg, 30 cm -> 0.3 m, 500 g -> 0.5 kg,
        5초 -> 5 s, 2 m/s² -> 2 m/s^2.
    """
    t = text.strip()
    # 첨자 숫자(v₀, ω₀, m₁, m₂ 등)를 일반 숫자로 — 기호 팔레트/교재 입력 대응
    t = t.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    replacements = {
        "㎏": "kg",
        "ｋｇ": "kg",
        "㎝": "cm",
        "㎜": "mm",
        "㎞": "km",
        "ｍ": "m",
        "Ｎ": "N",
        "㎨": "m/s^2",
        "㎧": "m/s",
        "μ": "mu",
        "µ": "mu",
        "τ": "tau",
        "ω": "omega",
        "α": "alpha",
        "θ": "theta",
        "–": "-",
        "−": "-",
        "×": "*",
        "·": "*",
        "²": "^2",
        "⁻": "^-",
        "초기속도": "초속도",
        "초기 속도": "초속도",
        "초기속력": "초속도",
        "초기 속력": "초속도",
        "처음 속도": "초속도",
        "처음속도": "초속도",
        "처음 속력": "초속도",
        "처음속력": "초속도",
        "나중 속도": "최종속도",
        "나중속도": "최종속도",
        "최종 속도": "최종속도",
        "최종 속력": "최종속도",
        "나중 속력": "최종속도",
        "최대 속도": "최대속도",
        "최소 속도": "최소속도",
        "설계 속도": "설계속도",
        "걸린 시간": "걸리는 시간",
        "소요 시간": "소요시간",
        "발사 속도": "발사속도",
        "발사 속력": "발사속도",
        "스프링상수": "스프링 상수",
        "용수철상수": "스프링 상수",
        "도르레": "도르래",
        "매끄런": "매끄러운",
        "마찰 업는": "마찰 없는",
        "쵸속도": "초속도",
        "구해 줘": "구하라",
        "구해줘": "구하라",
        "알려 줘": "구하라",
        "알려줘": "구하라",
        "마찰 계수": "마찰계수",
        "관성 모멘트": "관성모멘트",
        "질량 중심": "질량중심",
        "미끄럼 없이": "미끄러지지 않고",
        "미끄러지지 않게": "미끄러지지 않고",
        "마찰이 없고": "마찰이 없는",
        "마찰 없이": "마찰 없는",
    }
    for a, b in replacements.items():
        t = t.replace(a, b)

    # 각도
    t = t.replace("°", " deg ")
    def _deg_repl(m: re.Match) -> str:
        # 온도 문맥("실험실 온도는 20도")의 'N도'는 각도가 아니다.
        ctx = m.string[max(0, m.start() - 10):m.start()]
        if any(w in ctx for w in ["온도", "기온", "섭씨", "화씨", "체온"]):
            return m.group(0)
        return f"{m.group(1)} deg"

    t = re.sub(rf"{_NUM}\s*도", _deg_repl, t)

    # 한국어 단위 표기 정리
    unit_words = [
        # 긴 복합 단위를 먼저 치환해야 "뉴턴미터"가 "뉴턴"+"미터"로 쪼개지지 않는다.
        (r"킬로그램미터제곱", "kg*m^2"),
        (r"뉴턴미터", "N*m"),
        (r"미터퍼세컨드제곱", "m/s^2"),
        (r"미터매초제곱", "m/s^2"),
        (r"킬로그램", "kg"),
        (r"그램", "g"),
        (r"킬로미터", "km"),
        (r"센티미터", "cm"),
        (r"밀리미터", "mm"),
        (r"미터", "m"),
        (r"초", "s"),
        (r"분", "min"),
        (r"뉴턴", "N"),
        (r"줄", "J"),
        (r"주울", "J"),
        (r"라디안", "rad"),
    ]
    for ko, unit in unit_words:
        t = re.sub(rf"{_NUM}\s*{ko}", lambda m, unit=unit: f"{m.group(1)} {unit}", t)

    # 학생들이 붙여 쓰는 ASCII/한국어 단위 표현
    t = re.sub(r"미터\s*퍼\s*세컨드\s*제곱", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"미터퍼세컨드제곱", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"미터\s*매\s*초\s*제곱", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"m\s*/\s*s\s*(?:\^\s*2|²|2)", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"rad\s*/\s*s\s*(?:\^\s*2|²|2)", "rad/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"kg\s*m\s*(?:\^\s*2|²|2)(?!\s*(?:=|:))", "kg*m^2", t, flags=re.IGNORECASE)
    t = re.sub(r"kg\s+meter\s*(?:\^\s*2|squared)", "kg*m^2", t, flags=re.IGNORECASE)
    t = re.sub(r"N\s*[-·*]?\s*m\b", "N*m", t, flags=re.IGNORECASE)

    # 단위 조합: m/s, m/s^2, rad/s, rad/s^2, N/m, N*m
    t = re.sub(r"m\s*/\s*s\s*\^?\s*2", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"m\s*/\s*s2", "m/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"m\s*/\s*s", "m/s", t, flags=re.IGNORECASE)
    t = re.sub(r"rad\s*/\s*s\s*\^?\s*2", "rad/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"rad\s*/\s*s2", "rad/s^2", t, flags=re.IGNORECASE)
    t = re.sub(r"rad\s*/\s*s", "rad/s", t, flags=re.IGNORECASE)
    t = re.sub(r"N\s*/\s*m", "N/m", t, flags=re.IGNORECASE)
    t = re.sub(r"N\s*\*?\s*m", "N*m", t, flags=re.IGNORECASE)
    t = re.sub(r"kg\s*\*?\s*m\s*\^?\s*2(?!\s*(?:=|:))", "kg*m^2", t, flags=re.IGNORECASE)
    t = re.sub(r"kgm\s*\^?\s*2", "kg*m^2", t, flags=re.IGNORECASE)

    # SI 변환: 파서 내부는 m, kg, s 기준으로 처리한다.
    # 속도/가속도 단위를 먼저 변환해야 길이 단위 변환과 충돌하지 않는다.
    t = _convert_unit(rf"{_NUM}\s*cm\s*/\s*s\s*\^?\s*2", t, 0.01, "m/s^2")
    t = _convert_unit(rf"{_NUM}\s*mm\s*/\s*s\s*\^?\s*2", t, 0.001, "m/s^2")
    t = _convert_unit(rf"{_NUM}\s*km\s*/\s*s\s*\^?\s*2", t, 1000.0, "m/s^2")
    t = _convert_unit(rf"{_NUM}\s*cm\s*/\s*s", t, 0.01, "m/s")
    t = _convert_unit(rf"{_NUM}\s*mm\s*/\s*s", t, 0.001, "m/s")
    t = _convert_unit(rf"{_NUM}\s*km\s*/\s*s", t, 1000.0, "m/s")
    # km/h, km/hr, km/시
    t = _convert_unit(rf"{_NUM}\s*km\s*/\s*(?:h|hr|hour|시)", t, 1000.0 / 3600.0, "m/s")

    # 길이, 질량, 시간
    t = _convert_unit(rf"{_NUM}\s*cm(?=[^a-zA-Z]|$)", t, 0.01, "m")
    t = _convert_unit(rf"{_NUM}\s*mm(?=[^a-zA-Z]|$)", t, 0.001, "m")
    t = _convert_unit(rf"{_NUM}\s*km(?=[^a-zA-Z]|$)", t, 1000.0, "m")
    t = _convert_unit(rf"{_NUM}\s*g(?=[^a-zA-Z]|$)", t, 0.001, "kg")
    t = _convert_unit(rf"{_NUM}\s*min(?=[^a-zA-Z]|$)", t, 60.0, "s")

    # 붙어 있는 단위도 분리: 5kg -> 5 kg, 10m/s -> 10 m/s
    t = re.sub(rf"{_NUM}\s*(kg|m/s\^2|m/s|rad/s\^2|rad/s|N/m|N\*m|N|J|m|s|kg\*m\^2)\b", r"\1 \2", t, flags=re.IGNORECASE)
    # 위 substitution은 group이 두 개라 결과가 이상해질 수 있어 재보정
    t = re.sub(rf"{_NUM}\s+(kg|m/s\^2|m/s|rad/s\^2|rad/s|N/m|N\*m|N|J|m|s|kg\*m\^2)\b", r"\1 \2", t, flags=re.IGNORECASE)

    # 실제로는 위 2줄이 이미 충분하지만, '5 kg' 형태 유지 확인을 위해 공백만 정리한다.
    t = re.sub(r"\s+", " ", t).strip()
    return t


_IRRELEVANT_SENTENCE_MARKERS = (
    "관찰자의 질량",
    "실험실 온도",
    "교실 온도",
    "바깥 기온",
    "오늘 날씨",
    "벽시계",
    "실험 날짜",
    "팀 번호",
    "학생 수",
    "실험을 지켜봤",
    "책상의 색",
    "교실 책상의 길이",
)


def strip_irrelevant_background(text: str) -> str:
    """Remove only clearly labelled background sentences before extraction.

    This is intentionally conservative: it does not delete an arbitrary clause
    merely because it contains an unfamiliar number. Raw text is still retained
    in CanonicalProblem for provenance and the student-facing diagnosis.
    """
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", text) if part.strip()]
    if len(sentences) < 2:
        return text
    retained = [
        sentence
        for sentence in sentences
        if not any(marker in sentence for marker in _IRRELEVANT_SENTENCE_MARKERS)
    ]
    return " ".join(retained) if retained else text


def lower_for_match(text: str) -> str:
    return normalize(text).lower()
