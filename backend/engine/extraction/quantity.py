import re
from engine.models import Quantity

_NUM = r"(-?\d+(?:,\d{3})*(?:\.\d+)?)"


def _float(s: str) -> float:
    return float(s.replace(",", ""))


def first_number(pattern: str, text: str) -> tuple[float, str] | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    return _float(m.group(1)), m.group(0)


def _set(knowns: dict[str, Quantity], key: str, value: float, unit: str | None, source: str) -> None:
    # 명시적인 표기가 먼저 들어온 경우는 덮어쓰지 않는다.
    if key not in knowns:
        knowns[key] = Quantity(key, value, unit, source)




def _set_si_velocity(knowns: dict[str, Quantity], key: str, value: float, unit: str, source: str) -> None:
    if unit in {"km/h", "kmph", "km/hr"}:
        _set(knowns, key, value / 3.6, "m/s", source + " → m/s")
    else:
        _set(knowns, key, value, "m/s", source)


def _set_si_acceleration(knowns: dict[str, Quantity], key: str, value: float, unit: str, source: str) -> None:
    if unit.startswith("cm/s"):
        _set(knowns, key, value / 100.0, "m/s^2", source + " → m/s²")
    else:
        _set(knowns, key, value, "m/s^2", source)


def _unit_value(pattern: str, text: str) -> tuple[float, str, str] | None:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    return _float(m.group("num")), m.group("unit"), m.group(0)


def _has(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _label_value(label: str, text: str, unit_pattern: str | None = None) -> tuple[float, str] | None:
    unit = unit_pattern or r""
    return first_number(rf"(?:{label})\s*(?:=|:|은|는|이|가|의|는\s*)?[^\d-]{0,12}{_NUM}\s*{unit}", text)


def extract_quantities(text: str) -> dict[str, Quantity]:
    knowns: dict[str, Quantity] = {}
    raw = text
    compact = re.sub(r"\s+", "", text.lower())

    # ------------------------------------------------------------------
    # 암시적 초기/최종 조건
    # ------------------------------------------------------------------
    # 한국어 교재에서 자주 나오는 표현: "정지 상태에서 출발", "가만히 있다가".
    if _has(raw, [r"정지\s*상태에서\s*출발", r"정지\s*상태(?:의|인)?\s*물체", r"정지해\s*있다가", r"정지해\s*있는", r"멈춰\s*있는", r"가만히\s*있다가", r"처음(?:에는)?\s*가만히", r"처음(?:에는)?\s*정지", r"초기\s*정지", r"from\s+rest", r"initially\s+at\s+rest"]):
        _set(knowns, "v0", 0.0, "m/s", "정지 상태에서 출발 → v0=0")
    # "멈출 때까지", "최종적으로 정지"는 최종속도 0으로 본다.
    if _has(raw, [r"멈출\s*때", r"정지할\s*때", r"멈춘다", r"정지한다", r"최종적으로\s*정지", r"나중(?:에는)?\s*정지", r"comes\s+to\s+rest", r"until\s+it\s+stops"]):
        _set(knowns, "vf", 0.0, "m/s", "멈춤/최종 정지 → vf=0")

    # ------------------------------------------------------------------
    # 각도
    # ------------------------------------------------------------------
    angle = first_number(_NUM + r"\s*(?:deg|degree|degrees)", text)
    if angle:
        _set(knowns, "theta", angle[0], "deg", angle[1])

    # ------------------------------------------------------------------
    # 질량: m1=2 kg, 물체 A 2 kg, 질량 5 kg, 500 g→0.5 kg 등
    # ------------------------------------------------------------------
    m1 = first_number(r"(?:m1|m_1|m_a|mass\s*1|물체\s*1|물체\s*a|블록\s*1|블록\s*a|왼쪽\s*물체|수평면\s*위\s*물체|첫\s*번째\s*물체|1번\s*물체)[^\d-]{0,12}" + _NUM + r"\s*kg", text)
    m2 = first_number(r"(?:m2|m_2|m_b|mass\s*2|물체\s*2|물체\s*b|블록\s*2|블록\s*b|오른쪽\s*물체|매달린\s*물체|두\s*번째\s*물체|2번\s*물체)[^\d-]{0,12}" + _NUM + r"\s*kg", text)
    single_m = first_number(r"(?<![A-Za-z0-9_])m\s*(?:=|:|은|는)\s*" + _NUM + r"\s*kg", text)
    masses = re.findall(_NUM + r"\s*kg(?!\s*\*?\s*m|m)", text, flags=re.IGNORECASE)
    if single_m:
        _set(knowns, "m", single_m[0], "kg", single_m[1])
    if m1:
        _set(knowns, "m1", m1[0], "kg", m1[1])
    if m2:
        _set(knowns, "m2", m2[0], "kg", m2[1])
    if "m" not in knowns and "m1" not in knowns and masses:
        _set(knowns, "m", _float(masses[0]), "kg", masses[0] + " kg")
    if "m" not in knowns and "m1" not in knowns and len(masses) >= 2:
        knowns.pop("m", None)
        _set(knowns, "m1", _float(masses[0]), "kg", masses[0] + " kg")
        _set(knowns, "m2", _float(masses[1]), "kg", masses[1] + " kg")
    if re.search(r"(?:두|both)\s*매달린\s*물체", text, re.IGNORECASE) and len(masses) >= 2:
        knowns.pop("m", None)
        knowns.pop("m1", None)
        knowns.pop("m2", None)
        _set(knowns, "m1", _float(masses[0]), "kg", masses[0] + " kg")
        _set(knowns, "m2", _float(masses[1]), "kg", masses[1] + " kg")

    # Grams fallback for single-particle mass: 500 g -> 0.5 kg.
    gram_mass = first_number(r"(?:질량|mass|m\s*=)[^\d-]{0,12}" + _NUM + r"\s*g(?![a-zA-Z/])", text)
    if gram_mass and "m" not in knowns and "m1" not in knowns:
        _set(knowns, "m", gram_mass[0] / 1000.0, "kg", gram_mass[1] + " → kg")

    mu = first_number(r"(?:mu|마찰계수|coefficient\s*of\s*friction)\s*(?:=|:|은|는|is)?[^\d-]{0,12}" + _NUM, text)
    if mu:
        _set(knowns, "mu", mu[0], None, mu[1])

    height = first_number(r"(?:높이\s*변화|높이차|높이|height|h\s*=)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if height:
        _set(knowns, "h", height[0], "m", height[1])

    # ------------------------------------------------------------------
    # Phase 40: 기호 팔레트식 단위 생략 입력 (v₀=0, ω₀=0, θ=30)
    # 명시적 "심볼=값" 형태에서 단위가 빠지면 SI 기본 단위로 해석한다.
    # (단위가 있는 기존 패턴이 먼저 잡고, _set은 첫 값을 유지하므로 안전.)
    # ------------------------------------------------------------------
    if "v0" not in knowns:
        bare = first_number(r"(?<![a-z0-9_])v_?0\s*=\s*" + _NUM + r"(?![\d.,]|\s*(?:m/s|km/h|cm/s|m\b|km\b))", text)
        if bare:
            _set(knowns, "v0", bare[0], "m/s", bare[1] + " (단위 생략 → m/s)")
    if "omega0" not in knowns:
        bare = first_number(r"(?<![a-z0-9_])omega_?0\s*=\s*" + _NUM + r"(?!\s*rad)", text)
        if bare:
            _set(knowns, "omega0", bare[0], "rad/s", bare[1] + " (단위 생략 → rad/s)")
    if "theta" not in knowns:
        bare = first_number(r"(?<![a-z0-9_])theta\s*=\s*" + _NUM + r"(?!\s*(?:deg|도|rad|°))", text)
        if bare:
            _set(knowns, "theta", bare[0], "deg", bare[1] + " (단위 생략 → deg)")

    # ------------------------------------------------------------------
    # Phase 35: 학생식 자연어 표현
    # ------------------------------------------------------------------
    # "3 m/s²로 움직인다/가속한다" — 라벨(가속도) 없이 값+단위+조사로 오는 가속도
    bare_a = first_number(_NUM + r"\s*m/s\^?2\s*(?:로|의\s*(?:일정한\s*)?(?:등)?가속도)", text)
    if bare_a and "a" not in knowns:
        _set(knowns, "a", bare_a[0], "m/s^2", bare_a[1])

    # 충돌 자연어: "A(물체)는 4 m/s", "첫 번째 물체가 3 m/s" → v1
    v1_nl = first_number(r"(?:첫\s*번째\s*물체|물체\s*A|A\s*물체|A[가는은이])(?:[^\d-]{0,6}\d+(?:\.\d+)?\s*kg[가는은이의]?)?[^\d-]{0,10}" + _NUM + r"\s*m/s", text)
    if v1_nl:
        _set(knowns, "v1", v1_nl[0], "m/s", v1_nl[1])
    # "B는 정지", "두 번째 물체는 (처음에) 가만히/정지" → v2 = 0
    if _has(raw, [r"(?:두\s*번째\s*물체|물체\s*B|B\s*물체|B[가는은이])[^.]{0,14}(?:정지|가만히|멈춰)"]):
        _set(knowns, "v2", 0.0, "m/s", "두 번째 물체 정지 → v2=0")
    v2_nl = first_number(r"(?:두\s*번째\s*물체|물체\s*B|B\s*물체|B[가는은이])(?:[^\d-]{0,6}\d+(?:\.\d+)?\s*kg[가는은이의]?)?[^\d-]{0,10}" + _NUM + r"\s*m/s", text)
    if v2_nl:
        _set(knowns, "v2", v2_nl[0], "m/s", v2_nl[1])

    # "X m 아래(의 지점)에 떨어진다" → 발사점 기준 낙하 높이 h=X (Δy=-X)
    below = first_number(_NUM + r"\s*m\s*(?:아래|낮은\s*곳|낮은\s*지점)[^.]{0,10}(?:떨어|착지|도달)", text)
    if below and "h" not in knowns:
        _set(knowns, "h", below[0], "m", below[1] + " → 발사점 아래 착지 (Δy = -h)")

    # "힘(의) 방향으로 5m 이동/밀었다/끌었다/작용한다" → 힘과 변위가 같은 방향 (θ=0)
    if _has(raw, [
        r"힘(?:의)?\s*방향(?:으로|을\s*따라)[^.\n]{0,24}(?:이동|움직|끌|밀|작용)",
        r"힘[^.\n]{0,30}(?:변위|이동)[^.\n]{0,20}(?:같은|동일한|나란한)\s*방향",
        r"(?:변위|이동)[^.\n]{0,30}힘[^.\n]{0,20}(?:같은|동일한|나란한)\s*방향",
        r"(?:같은|동일한|나란한)\s*방향[^.\n]{0,30}(?:힘|변위|이동)",
        r"힘과\s*(?:변위|이동)(?:는|가)?\s*(?:같은|동일한|나란한)\s*방향",
    ]):
        _set(knowns, "theta", 0.0, "deg", "힘과 변위의 명시적 같은 방향 → θ=0")

    # ------------------------------------------------------------------
    # 일/에너지/스프링
    # ------------------------------------------------------------------
    work = first_number(r"(?:알짜일|한\s*일|일|work|W\s*=)[^\d-]{0,12}" + _NUM + r"\s*(?:J|N\s*\*?\s*m|Nm)", text)
    if work:
        _set(knowns, "W", work[0], "J", work[1])

    stiffness = first_number(r"(?:스프링\s*상수|용수철\s*상수|spring\s*constant|stiffness|k\s*(?:=|:|은|는))[^\d-]{0,12}" + _NUM + r"\s*(?:N/m|N\s*/\s*m)", text)
    if not stiffness:
        stiffness = first_number(_NUM + r"\s*(?:N/m|N\s*/\s*m)[^.\n]{0,20}(?:스프링|용수철)", text)
    if stiffness:
        _set(knowns, "k", stiffness[0], "N/m", stiffness[1])

    compression = first_number(r"(?:압축량|압축된\s*길이|압축|늘어난\s*길이|변형량|변위\s*x|x\s*=)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if not compression:
        compression = first_number(_NUM + r"\s*m[^.\n]{0,20}?(?:압축|늘어|변형)", text)
    if compression:
        _set(knowns, "x", compression[0], "m", compression[1])

    amplitude = first_number(r"(?:진폭|amplitude|A\s*=)[^\d-]{0,12}" + _NUM + r"\s*m(?!/s)", text)  # a=3m/s² 오매치 방지 (Phase 40)
    if amplitude:
        _set(knowns, "A", amplitude[0], "m", amplitude[1])

    radius = first_number(r"(?:반지름|radius|r\s*=|R\s*=)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if not radius:
        # 순간중심/평면강체/슬롯 문제에서는 "거리 0.8 m"가 보통 r_B/A 또는 IC-점 거리입니다.
        radius = first_number(r"(?:순간중심|순간\s*중심|IC|평면\s*강체[^.\n]{0,90}?거리|강체\s*평면운동[^.\n]{0,90}?거리|A\s*B\s*거리|AB\s*거리|A와\s*B\s*사이\s*거리|A점과\s*B점\s*사이\s*거리|두\s*점\s*사이|점\s*사이|A에서\s*B까지|B에서\s*A까지|핀의\s*위치|슬롯\s*내\s*위치|위치\s*r)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if radius:
        _set(knowns, "R", radius[0], "m", radius[1])
        _set(knowns, "r", radius[0], "m", radius[1])

    # ------------------------------------------------------------------
    # 운동학 변수
    # ------------------------------------------------------------------
    explicit_initial_kmh = _unit_value(r"(?P<num>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>km/h|km\s*/\s*h|kmph|km/hr)\s*(?:에서|로\s*달리다가|로\s*움직이다가|로\s*가다가|에서\s*출발|로\s*출발|로)", text)
    if explicit_initial_kmh:
        _set_si_velocity(knowns, "v0", explicit_initial_kmh[0], explicit_initial_kmh[1].replace(" ", ""), explicit_initial_kmh[2])

    explicit_throw_kmh = _unit_value(r"(?P<num>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>km/h|km\s*/\s*h|kmph|km/hr)\s*(?:의\s*)?(?:속력|속도)?(?:으로|로)\s*(?:던졌|던진|발사)", text)
    if explicit_throw_kmh:
        _set_si_velocity(knowns, "v0", explicit_throw_kmh[0], explicit_throw_kmh[1].replace(" ", ""), explicit_throw_kmh[2])

    speed_unit = r"(?P<unit>m/s|mps|km/h|km\s*/\s*h|kmph|km/hr)"
    v0 = _unit_value(r"(?:v0|v_i|vi|u\s*=|초속도|발사속도|초기속도|처음\s*속도|처음에는|처음에|initial\s*speed|initial\s*velocity)[^\d-]{0,12}(?P<num>" + _NUM[1:-1] + r")\s*" + speed_unit, text)
    if not v0:
        v0 = _unit_value(r"(?P<num>" + _NUM[1:-1] + r")\s*" + speed_unit + r"\s*(?:에서|로\s*달리다가|로\s*움직이다가|로\s*가다가|에서\s*출발|로\s*출발|로)", text)
    vf = _unit_value(r"(?:vf|v_f|최종속도|나중\s*속도|마지막\s*속도|final\s*speed|final\s*velocity)[^\d-]{0,12}(?P<num>" + _NUM[1:-1] + r")\s*" + speed_unit, text)
    if not vf:
        vf = _unit_value(r"(?:속도가|속력은|속도는)[^\d\n.]{0,25}?(?P<num>" + _NUM[1:-1] + r")\s*" + speed_unit + r"\s*(?:가|이)?\s*(?:되|도달)", text)
    v = _unit_value(r"(?:속도|속력|speed|velocity|v\s*=)[^\d-]{0,12}(?P<num>" + _NUM[1:-1] + r")\s*" + speed_unit, text)
    if v0:
        _set_si_velocity(knowns, "v0", v0[0], v0[1].replace(" ", ""), v0[2])
    if vf:
        _set_si_velocity(knowns, "vf", vf[0], vf[1].replace(" ", ""), vf[2])
    if v and "v0" not in knowns and "vf" not in knowns:
        _set_si_velocity(knowns, "v", v[0], v[1].replace(" ", ""), v[2])
    if ("던졌" in text or "던진" in text or "발사" in text or "projectile" in text.lower()) and "v0" not in knowns:
        throw_speed = first_number(_NUM + r"\s*(?:m/s|mps)\s*(?:의\s*)?(?:초속도|발사속도)(?:로|으로)", text)
        if not throw_speed:
            throw_speed = first_number(_NUM + r"\s*(?:m/s|mps)[^\.\n]{0,32}?(?:던졌|던진|발사)", text)
        if not throw_speed:
            throw_speed = first_number(r"(?:수평으로|비스듬히)[^\.\n]{0,20}?" + _NUM + r"\s*(?:m/s|mps)", text)
        if throw_speed:
            _set(knowns, "v0", throw_speed[0], "m/s", throw_speed[1])
    if "vf" not in knowns:
        reached_v = first_number(r"(?:후|뒤|나중|최종)[^.\n]{0,30}?" + _NUM + r"\s*(?:m/s|mps)\s*(?:가|이)?\s*(?:되|도달)", text)
        if reached_v:
            _set(knowns, "vf", reached_v[0], "m/s", reached_v[1])

    # 충돌용 명시 속도 v1, v2, v1f, v2f
    velocity_labels = {
        "v1": r"(?:v1|v_1|물체\s*1[^,.;]{0,12}?속도|1번\s*물체[^,.;]{0,12}?속도)",
        "v2": r"(?:v2|v_2|물체\s*2[^,.;]{0,12}?속도|2번\s*물체[^,.;]{0,12}?속도)",
        "v1f": r"(?:v1f|v_1f|v1'|v_1'|물체\s*1[^,.;]{0,12}?충돌\s*후\s*속도)",
        "v2f": r"(?:v2f|v_2f|v2'|v_2'|물체\s*2[^,.;]{0,12}?충돌\s*후\s*속도)",
    }
    for key, label in velocity_labels.items():
        m = first_number(label + r"\s*(?:=|:|은|는|이|가)?\s*" + _NUM + r"\s*(?:m/s|mps)?", text)
        if m:
            _set(knowns, key, m[0], "m/s", m[1])

    # "충돌 전 속도는 각각 4 m/s, 0 m/s"처럼 라벨 없이 두 속도를 쓰는 한국어 문장을 보완합니다.
    if ("충돌" in text or "collision" in text.lower()) and ("v1" not in knowns or "v2" not in knowns):
        speed_values = re.findall(_NUM + r"\s*(?:m/s|mps)", text, flags=re.IGNORECASE)
        speed_numbers = [_float(x) for x in speed_values]
        # 초속도/최종속도 같은 단일 운동 문제는 피하고, m1/m2가 있는 충돌 문장에서만 순서대로 보완합니다.
        if "m1" in knowns and "m2" in knowns and len(speed_numbers) >= 2:
            _set(knowns, "v1", speed_numbers[0], "m/s", speed_values[0] + " m/s")
            _set(knowns, "v2", speed_numbers[1], "m/s", speed_values[1] + " m/s")
        # 자연어 충돌: "2kg 물체가 4m/s로 3kg 정지 물체와 충돌", 
        # "4m/s로 가다가 정지해 있는 2kg 물체와 충돌"처럼 두 번째 물체의 v2=0이
        # 말로만 주어지고 속도 숫자는 하나뿐인 경우를 보완합니다.
        elif "m1" in knowns and "m2" in knowns and len(speed_numbers) >= 1:
            second_body_rest = _has(raw, [
                r"(?:정지해\s*있는|정지한|멈춰\s*있는|가만히\s*있는)\s*(?:질량\s*)?\d+(?:\.\d+)?\s*kg\s*(?:물체|블록)?\s*(?:와|과)",
                r"\d+(?:\.\d+)?\s*kg\s*(?:짜리\s*)?(?:정지\s*물체|정지한\s*물체|정지해\s*있는\s*물체|가만히\s*있는\s*물체)\s*(?:와|과)",
                r"(?:두\s*번째\s*물체|물체\s*2|2번\s*물체|물체\s*B|B\s*물체|B[가는은이])[^.\n]{0,20}(?:정지|가만히|멈춰)",
            ])
            if second_body_rest:
                _set(knowns, "v1", speed_numbers[0], "m/s", speed_values[0] + " m/s")
                _set(knowns, "v2", 0.0, "m/s", "정지한 두 번째 충돌 물체 → v2=0")

    time = first_number(r"(?:시간|time|t\s*=)[^\d-]{0,12}" + _NUM + r"\s*s", text)
    if not time:
        time = first_number(_NUM + r"\s*s\s*(?:동안|후|뒤|간|작용|동안\s*운동|동안\s*이동|가속|운동|움직)", text)
    if time:
        _set(knowns, "t", time[0], "s", time[1])

    distance = first_number(r"(?:이동한\s*거리|수평거리|사거리|거리|변위|이동거리|displacement|distance|s\s*=|x\s*=)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if not distance:
        distance = first_number(_NUM + r"\s*m\s*(?:동안|만큼|를|을|으로)?\s*(?:이동|움직|간다|갔다|전진|미끄러|밀|당|끌|작용)", text)
    if distance:
        _set(knowns, "s", distance[0], "m", distance[1])

    acceleration = first_number(r"(?:가속도|감속도|acceleration|deceleration|a\s*=)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    if not acceleration:
        acceleration = first_number(r"(?:가속|감속|등가속도)[^\n.]{0,30}?" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    if not acceleration:
        acceleration = first_number(_NUM + r"\s*(?:m/s\^?2|m/s2|mps2|m/s²)\s*(?:의\s*)?(?:일정한\s*)?(?:가속도|감속도|가속|감속|등가속)", text)
    if not acceleration:
        acceleration = first_number(_NUM + r"\s*(?:m/s\^?2|m/s2|mps2|m/s²)\s*(?:로|으로)?\s*(?:가속|감속|등가속)", text)
    if acceleration:
        _set(knowns, "a", acceleration[0], "m/s^2", acceleration[1])
    else:
        acceleration_cm = first_number(r"(?:가속도|감속도|acceleration|deceleration|a\s*=)[^\d-]{0,12}" + _NUM + r"\s*(?:cm/s\^?2|cm/s2)", text)
        if not acceleration_cm:
            acceleration_cm = first_number(_NUM + r"\s*(?:cm/s\^?2|cm/s2)\s*(?:로|으로)?\s*(?:가속|감속|등가속)", text)
        if acceleration_cm:
            _set(knowns, "a", acceleration_cm[0] / 100.0, "m/s^2", acceleration_cm[1] + " → m/s²")

    force = first_number(r"(?:힘|force|f\s*=|F\s*=)[^\d-]{0,12}" + _NUM + r"\s*N", text)
    if not force:
        force = first_number(_NUM + r"\s*N[^.\n]{0,20}?(?:힘|작용|가해|밀|당)", text)
    if not force:
        # "힘은 변위와 같은 방향이며 크기는 10 N이다" — 라벨과 값 사이 수식어가 긴 교과서식.
        # 문장 경계(.)를 넘지 않는 브릿지만 허용해 다른 문장의 값 오염은 차단한다.
        force = first_number(r"힘[^.\n]{0,24}?크기[가는은]?[^\d.-]{0,6}" + _NUM + r"\s*N", text)
    if force:
        _set(knowns, "F", force[0], "N", force[1])

    torque = first_number(r"(?:토크|모멘트|torque|tau\s*=)[^\d-]{0,12}" + _NUM + r"\s*(?:N\s*\*?\s*m|Nm)", text)
    if torque:
        _set(knowns, "tau", torque[0], "N*m", torque[1])

    inertia = first_number(r"(?:관성모멘트|moment\s*of\s*inertia|I\s*=)[^\d-]{0,12}" + _NUM + r"\s*(?:kg\s*\*?\s*m\^?2|kgm\^?2)", text)
    if inertia:
        _set(knowns, "I", inertia[0], "kg*m^2", inertia[1])

    omega0 = first_number(r"(?:omega0|초기\s*각속도|처음\s*각속도)[^\d-]{0,12}" + _NUM + r"\s*(?:rad/s|radps)", text)
    omega = first_number(r"(?:omega|각속도)[^\d-]{0,12}" + _NUM + r"\s*(?:rad/s|radps)", text)
    alpha = first_number(r"(?:alpha|각가속도)[^\d-]{0,12}" + _NUM + r"\s*(?:rad/s\^?2|rad/s2)", text)
    if omega0:
        _set(knowns, "omega0", omega0[0], "rad/s", omega0[1])
    if omega:
        _set(knowns, "omega", omega[0], "rad/s", omega[1])
    if alpha:
        _set(knowns, "alpha", alpha[0], "rad/s^2", alpha[1])

    e = first_number(r"(?:반발계수|coefficient\s*of\s*restitution|e\s*=)[^\d-]{0,12}" + _NUM, text)
    if e:
        _set(knowns, "e", e[0], None, e[1])

    # ------------------------------------------------------------------
    # 고급 동역학: 극좌표/상대운동/평면강체
    # ------------------------------------------------------------------
    rdot = first_number(r"(?:r_dot|rdot|r\s*dot|반지름\s*방향\s*속도|방사\s*속도|radial\s*velocity)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)", text)
    rddot = first_number(r"(?:r_ddot|rddot|r\s*ddot|반지름\s*방향\s*가속도|방사\s*가속도|radial\s*acceleration)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    theta_dot = first_number(r"(?:theta_dot|thetadot|세타\s*닷|각속도|angular\s*velocity)[^\d-]{0,12}" + _NUM + r"\s*(?:rad/s|radps)", text)
    theta_ddot = first_number(r"(?:theta_ddot|thetaddot|세타\s*더블닷|각가속도|angular\s*acceleration)[^\d-]{0,12}" + _NUM + r"\s*(?:rad/s\^?2|rad/s2|radps2)", text)
    v_a = first_number(r"(?:vA|v_A|v\s*of\s*A|A점\s*속도|점\s*A\s*속도)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)", text)
    v_b = first_number(r"(?:vB|v_B|v\s*of\s*B|B점\s*속도|점\s*B\s*속도)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)", text)
    a_a = first_number(r"(?:aA|a_A|a\s*of\s*A|A점\s*가속도|점\s*A\s*가속도)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    if rdot:
        _set(knowns, "rdot", rdot[0], "m/s", rdot[1])
    if rddot:
        _set(knowns, "rddot", rddot[0], "m/s^2", rddot[1])
    if theta_dot:
        _set(knowns, "omega", theta_dot[0], "rad/s", theta_dot[1])
        _set(knowns, "thetadot", theta_dot[0], "rad/s", theta_dot[1])
    if theta_ddot:
        _set(knowns, "alpha", theta_ddot[0], "rad/s^2", theta_ddot[1])
        _set(knowns, "thetaddot", theta_ddot[0], "rad/s^2", theta_ddot[1])
    if v_a:
        _set(knowns, "vA", v_a[0], "m/s", v_a[1])
    if v_b:
        _set(knowns, "vB", v_b[0], "m/s", v_b[1])
    if a_a:
        _set(knowns, "aA", a_a[0], "m/s^2", a_a[1])

    vrel = first_number(r"(?:v_rel|vrel|상대속도|상대\s*속도|relative\s*velocity)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)", text)
    arel = first_number(r"(?:a_rel|arel|상대가속도|상대\s*가속도|relative\s*acceleration)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    a_b = first_number(r"(?:aB|a_B|a\s*of\s*B|B점\s*가속도|점\s*B\s*가속도)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)", text)
    pulley_inertia = first_number(r"(?:도르래\s*관성모멘트|pulley\s*inertia|I_p|Ip)[^\d-]{0,12}" + _NUM + r"\s*(?:kg\s*\*?\s*m\^?2|kgm\^?2)", text)
    pulley_radius = first_number(r"(?:도르래\s*반지름|pulley\s*radius|R_p|Rp)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if vrel:
        _set(knowns, "vrel", vrel[0], "m/s", vrel[1])
    if arel:
        _set(knowns, "arel", arel[0], "m/s^2", arel[1])
    if a_b:
        _set(knowns, "aB", a_b[0], "m/s^2", a_b[1])
    if pulley_inertia:
        _set(knowns, "Ip", pulley_inertia[0], "kg*m^2", pulley_inertia[1])
        _set(knowns, "I", pulley_inertia[0], "kg*m^2", pulley_inertia[1])
    if pulley_radius:
        _set(knowns, "Rp", pulley_radius[0], "m", pulley_radius[1])
        _set(knowns, "R", pulley_radius[0], "m", pulley_radius[1])


    # Explicit vector components for 2D rigid-body problems.
    component_patterns = {
        "vAx": r"(?:vAx|v_Ax|A점\s*x방향\s*속도|A점\s*속도\s*x성분)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)",
        "vAy": r"(?:vAy|v_Ay|A점\s*y방향\s*속도|A점\s*속도\s*y성분)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s|mps)",
        "aAx": r"(?:aAx|a_Ax|A점\s*x방향\s*가속도|A점\s*가속도\s*x성분)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)",
        "aAy": r"(?:aAy|a_Ay|A점\s*y방향\s*가속도|A점\s*가속도\s*y성분)[^\d-]{0,12}" + _NUM + r"\s*(?:m/s\^?2|m/s2|mps2)",
        "rBAx": r"(?:rBAx|r_BA_x|B의\s*A에\s*대한\s*x좌표|r_B/A\s*x성분)[^\d-]{0,12}" + _NUM + r"\s*m",
        "rBAy": r"(?:rBAy|r_BA_y|B의\s*A에\s*대한\s*y좌표|r_B/A\s*y성분)[^\d-]{0,12}" + _NUM + r"\s*m",
    }
    for key, pat in component_patterns.items():
        m = first_number(pat, text)
        if m:
            unit = "m/s^2" if key.startswith("a") else "m/s" if key.startswith("v") else "m"
            _set(knowns, key, m[0], unit, m[1])

    # Static/kinetic friction coefficient variants.
    mu_s = first_number(r"(?:mu_s|μs|정지마찰계수|정지\s*마찰계수)[^\d-]{0,12}" + _NUM, text)
    mu_k = first_number(r"(?:mu_k|μk|운동마찰계수|운동\s*마찰계수)[^\d-]{0,12}" + _NUM, text)
    if mu_s:
        _set(knowns, "mu_s", mu_s[0], None, mu_s[1])
        _set(knowns, "mu", mu_s[0], None, mu_s[1])
    if mu_k:
        _set(knowns, "mu_k", mu_k[0], None, mu_k[1])
        _set(knowns, "mu", mu_k[0], None, mu_k[1])

    # Projectile explicit heights.
    h0 = first_number(r"(?:초기\s*높이|출발\s*높이|y0|y_0)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    yf = first_number(r"(?:최종\s*높이|착지\s*높이|목표\s*높이|y_final|yf|y_f)[^\d-]{0,12}" + _NUM + r"\s*m", text)
    if h0:
        _set(knowns, "h0", h0[0], "m", h0[1])
    if yf:
        _set(knowns, "yf", yf[0], "m", yf[1])


    g = first_number(r"(?:g\s*=|중력가속도)[^\d-]{0,12}" + _NUM, text)
    knowns["g"] = Quantity("g", g[0] if g else 9.81, "m/s^2", g[1] if g else "기본값 9.81 m/s^2")
    return knowns
