
INERTIA_BETA = {
    "solid_sphere": 2/5,
    "hollow_sphere": 2/3,
    "solid_cylinder": 1/2,
    "disk": 1/2,
    "hoop": 1,
    "ring": 1,
}

KOREAN_BODY_TYPE_MAP = {
    "속이 찬 구": "solid_sphere",
    "실구": "solid_sphere",
    "구형 물체": "solid_sphere",
    "공": "solid_sphere",
    "속이 빈 구": "hollow_sphere",
    "얇은 구껍질": "hollow_sphere",
    "원판": "disk",
    "디스크": "disk",
    "실린더": "solid_cylinder",
    "원통": "solid_cylinder",
    "속이 찬 원통": "solid_cylinder",
    "고리": "hoop",
    "링": "ring",
    "바퀴": "hoop",
    "hoop": "hoop",
    "ring": "ring",
    "disk": "disk",
    "disc": "disk",
    "solid sphere": "solid_sphere",
    "hollow sphere": "hollow_sphere",
    "solid cylinder": "solid_cylinder",
}


def infer_body_shape(text: str) -> str | None:
    import re
    t = text.lower()
    # Longer phrases first.
    for ko, shape in sorted(KOREAN_BODY_TYPE_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        token = ko.lower()
        if token == "공":
            # Avoid false positives such as 공기저항.
            if re.search(r"공(이|은|을|의|과|,|\.|\s)", t):
                return shape
            continue
        if token in t:
            return shape
    # Single-letter Korean "구" is too broad because it appears in words such as
    # "구하라"; require it to behave like a noun.
    if re.search(r"구(가|는|를|의|와|,|\.|\s)", t):
        return "solid_sphere"
    return None


def beta_for_shape(shape: str | None) -> float | None:
    if not shape:
        return None
    return INERTIA_BETA.get(shape)
