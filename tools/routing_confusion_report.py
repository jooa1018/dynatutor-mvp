#!/usr/bin/env python3
"""Routing confusion-matrix & accuracy harness.

Answers, with numbers instead of guesses:
  1. 어떤 유형이 어떤 유형으로 새는가        (routing confusion matrix)
  2. solver별 precision / recall / support   (어디가 삼키고 어디가 굶는가)
  3. 상위 혼동 쌍                             (재설계 우선순위)
  4. 모호 케이스: top1-top2 점수 격차가 작음   (되묻기 후보 — 1단계 재설계 입력)
  5. 수치 정답률 (phase20_derived 129문항)    (오답 측정)
  6. negative 60문항 중 ok=True 오주장         (환각성 오탐)

Usage:
    cd backend
    python tools/routing_confusion_report.py            # full run
    python tools/routing_confusion_report.py --gap 10   # ambiguity threshold
    python tools/routing_confusion_report.py --limit 50 # quick pass

Output: reports/routing_confusion/report.{json,md}

Note on environment: if real `pint` is unavailable (offline sandbox), a minimal
exact-factor shim (tools/_pint_shim.py) is installed and the report is marked
`"units_backend": "shim"`. Re-run with real pint before trusting release-grade
numbers.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import types
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

UNITS_BACKEND = "pint"
try:  # pragma: no cover - environment dependent
    import pint  # noqa: F401
except ImportError:
    import tools._pint_shim as _shim

    _m = types.ModuleType("pint")
    _m.UnitRegistry = _shim.UnitRegistry
    _m.DimensionalityError = _shim.DimensionalityError
    sys.modules["pint"] = _m
    UNITS_BACKEND = "shim"

from engine.extraction.extractor import extract_problem  # noqa: E402
from engine.solvers.registry import SolverRegistry  # noqa: E402

BENCH = BACKEND / "tests" / "benchmarks"


# ---------------------------------------------------------------- loading
def load_routing_cases() -> list[dict]:
    """Cases with an expected solver label (routing ground truth)."""
    cases: list[dict] = []
    g300 = BENCH / "generated_300.json"
    if g300.exists():
        for i, row in enumerate(json.loads(g300.read_text(encoding="utf-8"))):
            cases.append({
                "id": f"g300_{i:03d}",
                "dataset": "generated_300",
                "problem": row["problem"],
                "expected_solver": row["solver"],
            })
    for path in sorted((BENCH / "phase20_derived").glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            case = {
                "id": row["id"],
                "dataset": f"phase20_derived/{path.stem}",
                "problem": row["problem_ko"],
                "expected_solver": row.get("expected_solver"),
                "topic": row.get("topic"),
            }
            if "expected_numeric" in row:
                case["expected_numeric"] = row["expected_numeric"]
                case["tolerance"] = row.get("tolerance", 1e-3)
            cases.append(case)
    return cases


def load_negative_cases() -> list[dict]:
    cases: list[dict] = []
    neg_dir = BENCH / "phase20_negative"
    if not neg_dir.exists():
        return cases
    for path in sorted(neg_dir.glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            cases.append({
                "id": row["id"],
                "dataset": f"phase20_negative/{path.stem}",
                "problem": row["problem_ko"],
                "topic": row.get("topic"),
                "expected_reason_contains": row.get("expected_reason_contains"),
            })
    return cases


# ---------------------------------------------------------------- perturbations
# Label-preserving Korean variations. Each transform must NOT change which
# solver is physically correct, what is being asked, or the correct answer.
# check_numeric=True → gold-numeric cases are re-solved under the transform
# (catches distractor-value injection and unit-parsing regressions).
import re as _re


def _question_first(t: str) -> str:
    """'상황. 질문을 구하라.' → '질문을 구하려 한다. 상황.' (문장 2개 이상일 때만)"""
    parts = [s.strip() for s in t.split(". ") if s.strip()]
    if len(parts) < 2:
        return t
    last = parts[-1]
    if not any(k in last for k in ["구하라", "구하시오", "얼마", "?"]):
        return t
    return last.rstrip(".") + ". 상황은 다음과 같다. " + ". ".join(parts[:-1]) + "."


PERTURBATIONS: list[dict] = [
    # --- 동의어 (교과서 표준 표현) ---
    {"name": "동의어: 구하라→계산하라", "fn": lambda t: t.replace("구하라", "계산하라"), "check_numeric": False},
    {"name": "동의어: 경사면→빗면", "fn": lambda t: t.replace("경사면", "빗면"), "check_numeric": False},
    {"name": "동의어: 마찰 없는→매끄러운", "fn": lambda t: t.replace("마찰 없는", "매끄러운").replace("마찰이 없는", "매끄러운"), "check_numeric": False},
    {"name": "동의어: 블록→물체", "fn": lambda t: t.replace("블록", "물체"), "check_numeric": False},
    {"name": "동의어: 스프링→용수철", "fn": lambda t: t.replace("스프링", "용수철"), "check_numeric": False},
    {"name": "동의어: 등가속도→일정한 가속도", "fn": lambda t: t.replace("등가속도", "일정한 가속도"), "check_numeric": False},
    {"name": "동의어: 속력→빠르기", "fn": lambda t: t.replace("속력", "빠르기"), "check_numeric": False},
    {"name": "동의어: 매달려→걸려", "fn": lambda t: t.replace("매달려", "걸려"), "check_numeric": False},
    {"name": "동의어: 충돌한다→부딪친다", "fn": lambda t: t.replace("충돌한다", "부딪친다").replace("충돌했다", "부딪쳤다"), "check_numeric": False},
    {"name": "동의어: 정지 상태에서→가만히 있다가", "fn": lambda t: t.replace("정지 상태에서", "가만히 있다가"), "check_numeric": False},
    {"name": "동의어: 수평 방향으로→수평하게", "fn": lambda t: t.replace("수평 방향으로", "수평하게"), "check_numeric": False},
    # --- 표기 변형 ---
    {"name": "표기: N도→N°", "fn": lambda t: _re.sub(r"(\d+(?:\.\d+)?)도(?![a-가-힣])", r"\1°", t), "check_numeric": True},
    {"name": "표기: 단위 유니코드(㎏ ㎞ ㎧)", "fn": lambda t: _re.sub(r"(\d) ?kg\b", r"\1㎏", _re.sub(r"(\d) ?km/h", r"\1㎞/h", _re.sub(r"(\d) ?m/s\b", r"\1㎧", t))), "check_numeric": True},
    {"name": "표기: 정수→소수(10→10.0)", "fn": lambda t: _re.sub(r"(?<![\d.])(\d+) (m/s|m|kg|N|s|km/h|cm|도)\b", r"\1.0 \2", t), "check_numeric": True},
    {"name": "표기: km/h→시속", "fn": lambda t: _re.sub(r"(\d+(?:\.\d+)?) ?km/h", r"시속 \1 km", t), "check_numeric": True},
    {"name": "띄어쓰기: '10 m/s'→'10m/s'", "fn": lambda t: _re.sub(r"(\d) (m/s|m|kg|N|s|km/h|cm)\b", r"\1\2", t), "check_numeric": True},
    # --- 구조 변형 ---
    {"name": "어순: 질문 먼저", "fn": _question_first, "check_numeric": False},
    {"name": "앞 filler 문장 추가", "fn": lambda t: "다음 동역학 문제를 풀어 보자. " + t, "check_numeric": False},
    {"name": "뒤 filler 문장 추가", "fn": lambda t: t + " 풀이 과정을 단계별로 보여라.", "check_numeric": False},
    # --- 방해문 (동음이의어·트랩 키워드·무관 숫자) ---
    {"name": "방해문: 무관 숫자(온도)", "fn": lambda t: t + " 참고로 실험실 온도는 20도였다.", "check_numeric": True},
    {"name": "방해문: 동음이의어 '줄'(대기열)", "fn": lambda t: t + " 학생들이 줄을 서서 실험 차례를 기다렸다.", "check_numeric": True},
    {"name": "방해문: 동음이의어 '일'(task)", "fn": lambda t: t + " 오늘 할 일이 많지만 이 문제부터 풀자.", "check_numeric": True},
    {"name": "방해문: 트랩 키워드 '수평면'", "fn": lambda t: t + " 실험 준비는 수평면이 잘 맞춰진 책상 위에서 했다.", "check_numeric": True},
    {"name": "방해문: 무관 거리 숫자", "fn": lambda t: t + " 관찰 카메라는 실험대에서 3 m 떨어져 있었다.", "check_numeric": True},
]


def run_perturbation_probe(registry: SolverRegistry, cases: list[dict], limit: int | None) -> dict:
    """3가지 불변량: (1) routing (2) requested_outputs (3) gold 수치 답."""
    base_cases = cases if limit is None else cases[:limit]
    # base reference per case (extract once)
    refs = []
    for case in base_cases:
        try:
            cp = extract_problem(case["problem"])
            refs.append((case, cp, set(cp.requested_outputs or [])))
        except Exception:
            continue

    probe = {"base_cases": len(refs), "transforms": [], "total_breaks": 0}
    for pert in PERTURBATIONS:
        name, fn, check_numeric = pert["name"], pert["fn"], pert["check_numeric"]
        applied = routing_broken = outputs_drift = numeric_broken = 0
        examples: list[dict] = []

        def note(kind: str, case: dict, detail: str, mutated: str):
            if len(examples) < 4:
                examples.append({"kind": kind, "id": case["id"], "detail": detail, "mutated": mutated[:120]})

        for case, cp_base, req_base in refs:
            expected = case["expected_solver"] or "(unlabeled)"
            try:
                mutated = fn(case["problem"])
            except Exception:
                continue
            if mutated == case["problem"]:
                continue
            applied += 1
            try:
                cp = extract_problem(mutated)
                matches = [m for s in registry.solvers if (m := s.match(cp))]
                matches.sort(key=lambda m: m.score, reverse=True)
                selected = matches[0].solver.name if matches else "(none)"
            except Exception as e:
                routing_broken += 1
                note("routing", case, f"crash {type(e).__name__}", mutated)
                continue

            if selected != expected:
                routing_broken += 1
                note("routing", case, f"{expected} → {selected} (system_type={cp.system_type})", mutated)
                continue  # 아래 불변량은 routing이 살아있을 때만 의미 있음

            if set(cp.requested_outputs or []) != req_base:
                outputs_drift += 1
                note("outputs", case, f"{sorted(req_base)} → {sorted(cp.requested_outputs or [])}", mutated)

            if check_numeric and "expected_numeric" in case and matches:
                try:
                    out = matches[0].solver.solve(cp)
                    actual = out.answer.numeric if (out.answer and out.answer.numeric is not None) else None
                    tol = float(case["tolerance"])
                    if actual is None or not math.isclose(float(actual), float(case["expected_numeric"]), rel_tol=tol, abs_tol=tol):
                        numeric_broken += 1
                        note("numeric", case, f"expected {case['expected_numeric']}, got {actual}", mutated)
                except Exception as e:
                    numeric_broken += 1
                    note("numeric", case, f"solve crash {type(e).__name__}: {e}", mutated)

        broken_total = routing_broken + outputs_drift + numeric_broken
        probe["transforms"].append({
            "name": name, "applied": applied,
            "routing_broken": routing_broken, "outputs_drift": outputs_drift, "numeric_broken": numeric_broken,
            "break_rate": round(broken_total / applied, 4) if applied else None,
            "examples": examples,
        })
        probe["total_breaks"] += broken_total
    return probe


# ------------------------------------------------- verification probe
import copy as _copy
from engine.verification.suite import verify_result


def _mutate(result, mode: str):
    r = _copy.deepcopy(result)
    def scale(x):
        if mode == "x1.1":
            return x * 1.1
        if mode == "sign":
            return -x
        return x
    if r.answer is not None and r.answer.numeric is not None:
        r.answer.numeric = scale(float(r.answer.numeric))
    for a in r.answers or []:
        if a.numeric is not None:
            a.numeric = scale(float(a.numeric))
    if mode == "unit":
        wrong = {"m/s": "m/s²", "m/s²": "m/s", "m": "s", "s": "m", "N": "J", "J": "N",
                 "rad/s": "rad/s²", "rad/s²": "rad/s", "N·s": "J", "N*s": "J"}
        if r.answer is not None and r.answer.unit in wrong:
            r.answer.unit = wrong[r.answer.unit]
        for a in r.answers or []:
            if a.unit in wrong:
                a.unit = wrong[a.unit]
    return r


def run_verification_probe(registry: SolverRegistry, cases: list[dict], limit: int | None) -> dict:
    """검증 스위트 측정: 무고 오탐(FP)=0 이어야 하고, 오염 검출률(민감도)을 잰다."""
    base = cases if limit is None else cases[:limit]
    from collections import defaultdict
    per_type = defaultdict(lambda: {"n": 0, "fp": 0, "x1.1": 0, "sign": 0, "unit": 0, "covered": 0})
    totals = {"n": 0, "fp": 0, "x1.1": 0, "sign": 0, "unit": 0, "covered": 0}
    fp_examples, escape_examples = [], []
    seen_problem = set()
    for case in base:
        if case["problem"] in seen_problem:
            continue
        seen_problem.add(case["problem"])
        try:
            cp = extract_problem(case["problem"])
            matches = sorted([m for s in registry.solvers if (m := s.match(cp))], key=lambda m: -m.score)
            if not matches:
                continue
            result = matches[0].solver.solve(cp)
            if not result.ok:
                continue
        except Exception:
            continue
        st = cp.system_type
        rec, totals["n"] = per_type[st], totals["n"] + 1
        rec["n"] += 1
        clean = verify_result(cp, result)
        covered = any(c.startswith("역대입:") for c in clean.checks)
        if covered:
            rec["covered"] += 1; totals["covered"] += 1
        if clean.errors:
            rec["fp"] += 1; totals["fp"] += 1
            if len(fp_examples) < 5:
                fp_examples.append({"type": st, "errors": clean.errors[:2], "problem": case["problem"][:80]})
            continue
        for mode in ("x1.1", "sign", "unit"):
            mutated = _mutate(result, mode)
            rep = verify_result(cp, mutated)
            if rep.errors:
                rec[mode] += 1; totals[mode] += 1
            elif mode == "x1.1" and covered and len(escape_examples) < 5:
                escape_examples.append({"type": st, "mode": mode, "problem": case["problem"][:80]})
    return {
        "totals": totals,
        "per_type": {k: dict(v) for k, v in sorted(per_type.items())},
        "fp_examples": fp_examples,
        "escape_examples": escape_examples,
    }


# ------------------------------------------------- provenance probe
from engine.verification.provenance import analyze as _analyze_prov

INJECTORS = [
    ("배경 질량(m)", " 참고로 저울의 질량 2 kg 추는 사용하지 않았다."),
    ("배경 시간(t)", " 이 문제는 시험 시간 60 초 안에 풀어야 한다."),
    ("배경 힘(F)", " 옆 반 학생은 힘 5 N 문제를 풀고 있었다."),
    ("배경 높이(h)", " 참고로 실험 기록지에는 높이 1 m 선반이 그려져 있다."),
    ("배경 각도(theta)", " 참고로 칠판에는 각도 25도 예제가 남아 있었다."),
]


def run_provenance_probe(registry: SolverRegistry, cases: list[dict], limit: int | None) -> dict:
    """주입 검출률: 배경 문장이 실제로 known을 주입한 케이스에서
    provenance가 (a) 플래그하는가 (b) 사용/미사용에 따라 error/warning으로
    올바르게 에스컬레이션하는가."""
    base_cases = cases if limit is None else cases[:limit]
    seen = set()
    result = {"clean_fp": 0, "injectors": [], "landed_total": 0, "detected_total": 0}
    # clean FP (suite 레벨이 아닌 provenance 레벨)
    base_refs = []
    for case in base_cases:
        if case["problem"] in seen:
            continue
        seen.add(case["problem"])
        try:
            cp = extract_problem(case["problem"])
        except Exception:
            continue
        result["clean_fp"] += len(_analyze_prov(cp).suspicious_entries)
        base_refs.append((case, cp, set(cp.knowns.keys())))

    from engine.verification.suite import verify_result as _verify
    for name, sentence in INJECTORS:
        landed = detected = withheld = warned = solver_ignored = 0
        examples = []
        for case, cp_base, base_keys in base_refs:
            try:
                cp = extract_problem(case["problem"] + sentence)
            except Exception:
                continue
            new_keys = set(cp.knowns.keys()) - base_keys
            if not new_keys:
                continue
            # ground truth: 값+단위 표기가 '주입 문장에만' 있는 키만 must-flag.
            # (주입이 기존 값을 m→m1로 개명시키는 재구조화 부작용이 있어,
            #  개명된 정당한 값까지 플래그를 요구하면 안 된다.)
            from engine.extraction.normalizer import normalize as _norm
            base_norm, inj_norm = _norm(case["problem"]), _norm(sentence)
            must_flag = set()
            for k in new_keys:
                snip = getattr(cp.knowns[k], "source_text", "") or ""
                in_inj = snip in inj_norm
                in_base = snip in base_norm
                if in_inj and not in_base:
                    must_flag.add(k)
                elif in_inj and in_base:
                    must_flag.add(k)  # 다의적 — ambiguous 플래그로 커버되어야 함
            if not must_flag:
                continue
            landed += 1
            prov = _analyze_prov(cp)
            flagged = {e.symbol for e in prov.suspicious_entries} | {e.symbol for e in prov.ambiguous_entries}
            if must_flag <= flagged:
                detected += 1
            elif len(examples) < 3:
                examples.append({"id": case["id"], "missed": sorted(must_flag - flagged)})
            # suite 에스컬레이션 확인 (routing이 살아있는 경우만)
            try:
                matches = sorted([m for s in registry.solvers if (m := s.match(cp))], key=lambda m: -m.score)
                if matches:
                    out = matches[0].solver.solve(cp)
                    if out.ok:
                        rep = _verify(cp, out)
                        if any(e.startswith("출처 의심") for e in rep.errors):
                            withheld += 1
                        elif any(w.startswith("출처 의심") for w in rep.warnings):
                            warned += 1
                        else:
                            solver_ignored += 1
            except Exception:
                pass
        result["landed_total"] += landed
        result["detected_total"] += detected
        result["injectors"].append({
            "name": name, "landed": landed, "detected": detected,
            "withheld_error": withheld, "kept_with_warning": warned,
            "missed_examples": examples,
        })
    return result


# ------------------------------------------------- clarify probe
from engine.routing.clarify import apply_clarify_patch, build_clarification

# 제작 모호 세트: (문제, 기대 규칙, 해소 patch 또는 None)
CLARIFY_CASES = [
    ("30도 경사면 위 블록의 가속도를 구하라.", "incline_friction_unknown",
     {"subtype": "no_friction", "assume": "마찰 무시"}),
    ("경사각 25도 빗면에서 물체가 미끄러진다. 가속도는?", "incline_friction_unknown",
     {"subtype": "no_friction", "assume": "마찰 무시"}),
    ("블록이 도르래 줄에 연결된 채 30도 경사면 위에 놓여 있다. 가속도는?", "pulley_topology_unknown", None),
    ("두 물체가 줄과 도르래로 연결되어 있다. 가속도를 구하라.", "pulley_topology_unknown", None),
    ("30도 경사면 위에서 블록이 용수철에 연결되어 있다. 블록을 놓으면 속도는?", "mixed_spring_conflict",
     {"system_type": "spring_energy", "assume": "경사면 무시"}),
    ("공을 45도로 발사했다. 사거리는?", "missing_values",
     {"set_known": {"symbol": "v0", "unit": "m/s", "label": "초속도", "value": 20}}),
    ("스프링 상수 200N/m인 진동계의 주기를 구하라.", "missing_values",
     {"set_known": {"symbol": "m", "unit": "kg", "label": "질량", "value": 0.5}}),
    ("질량 2kg와 3kg인 두 공이 정면 충돌한다. 충돌 후 속도는?", "missing_values", None),
    # ---- Phase 34 확장 규칙 ----
    ("평면강체에서 A와 B 사이 거리는 0.7m, 각속도는 3rad/s이다. B점 속도는?", "rigid_missing_reference",
     {"set_known": {"symbol": "vA", "value": 0.0, "unit": "m/s", "label": "A점 고정(vA=0)"}, "assume": "A점 고정"}),
    ("용수철 장치가 있다. 무엇을 구할 수 있을까?", "unknown_with_evidence",
     {"system_type": "spring_energy", "assume": "용수철 모형으로 해석"}),
    ("커브 도로가 있다. 이 상황을 설명하라.", "unknown_with_evidence",
     {"system_type": "flat_curve_friction", "assume": "커브 주행 모형으로 해석"}),
    ("등가속도 상황이다. 무엇을 구할 수 있는가?", "missing_values", None),
    ("물체가 구르는 상황이다. 설명하라.", "evidence_confirm",
     {"system_type": "pure_rolling_energy", "assume": "순수 구름 모형으로 해석"}),
    ("m1=10kg가 30도 경사면 위에 있고 m2=1kg가 매달려 있다. 가속도는?", "incline_hanging_candidate",
     {"system_type": "pulley_incline_hanging", "assume": "줄/도르래 연결"}),
]


def run_clarify_probe(registry: SolverRegistry, cases: list[dict], negatives: list[dict], limit: int | None) -> dict:
    base = cases if limit is None else cases[:limit]
    # 1) FP: 벤치마크에서 되묻기가 뜨면 안 된다 (전부 풀리는 문제).
    fp = []
    seen = set()
    for case in base:
        if case["problem"] in seen:
            continue
        seen.add(case["problem"])
        try:
            cp = extract_problem(case["problem"])
            matches = sorted([m for s in registry.solvers if (m := s.match(cp))], key=lambda m: -m.score)
            fired = None
            if not matches:
                fired = build_clarification(cp)
            else:
                r = matches[0].solver.solve(cp)
                if not r.ok:
                    fired = build_clarification(cp)
            if fired is not None:
                fp.append({"id": case["id"], "rule": fired.rule, "problem": case["problem"][:70]})
        except Exception:
            continue

    # 2) 제작 모호 세트: 발동 + 규칙 일치 + 해소
    crafted = []
    for prob, expected_rule, res_patch in CLARIFY_CASES:
        cp = extract_problem(prob)
        matches = sorted([m for s in registry.solvers if (m := s.match(cp))], key=lambda m: -m.score)
        clar = None
        if not matches:
            clar = build_clarification(cp)
        else:
            r = matches[0].solver.solve(cp)
            if not r.ok:
                clar = build_clarification(cp)
        row = {"problem": prob[:56], "expected": expected_rule,
               "fired": clar.rule if clar else None,
               "rule_ok": bool(clar and clar.rule == expected_rule),
               "resolved": None}
        if res_patch is not None:
            cp2 = extract_problem(prob)
            try:
                apply_clarify_patch(cp2, res_patch)
                ms2 = sorted([m for s in registry.solvers if (m := s.match(cp2))], key=lambda m: -m.score)
                out = ms2[0].solver.solve(cp2) if ms2 else None
                if out and out.ok:
                    row["resolved"] = True
                else:
                    # 해소 실패가 아니라 다음 질문으로 연쇄되는지 확인
                    nxt = build_clarification(cp2)
                    row["resolved"] = f"chained→{nxt.rule}" if nxt else False
            except Exception as e:
                row["resolved"] = f"error: {type(e).__name__}"
        crafted.append(row)

    # 3) negative: 되묻기 전환율 (정보성 — 거절보다 나은 대화가 되는 비율)
    neg_clar = 0
    neg_rules: Counter = Counter()
    for case in negatives:
        try:
            cp = extract_problem(case["problem"])
            matches = sorted([m for s in registry.solvers if (m := s.match(cp))], key=lambda m: -m.score)
            clar = None
            if not matches:
                clar = build_clarification(cp)
            else:
                r = matches[0].solver.solve(cp)
                if not r.ok:
                    clar = build_clarification(cp)
            if clar is not None:
                neg_clar += 1
                neg_rules[clar.rule] += 1
        except Exception:
            continue

    return {
        "fp": fp,
        "crafted": crafted,
        "crafted_fired": sum(1 for c in crafted if c["fired"]),
        "crafted_rule_ok": sum(1 for c in crafted if c["rule_ok"]),
        "crafted_resolved": sum(1 for c in crafted if c["resolved"] is True or (isinstance(c["resolved"], str) and c["resolved"].startswith("chained"))),
        "crafted_resolvable": sum(1 for c in crafted if c["resolved"] is not None),
        "negatives_with_clarification": neg_clar,
        "negatives_total": len(negatives),
        "negative_rule_distribution": dict(neg_rules),
    }


# ---------------------------------------------------------------- run
def run(gap_threshold: int, limit: int | None) -> dict:
    registry = SolverRegistry()
    routing_cases = load_routing_cases()
    negative_cases = load_negative_cases()
    if limit:
        routing_cases = routing_cases[:limit]
        negative_cases = negative_cases[: max(1, limit // 5)]

    confusion: Counter = Counter()
    per_solver = defaultdict(lambda: {"support": 0, "correct": 0, "selected_total": 0})
    mismatches: list[dict] = []
    ambiguous: list[dict] = []
    numeric = {"checked": 0, "passed": 0, "failures": []}
    errors: list[dict] = []

    t0 = time.time()
    for case in routing_cases:
        expected = case["expected_solver"] or "(unlabeled)"
        try:
            cp = extract_problem(case["problem"])
            matches = [m for s in registry.solvers if (m := s.match(cp))]
            matches.sort(key=lambda m: m.score, reverse=True)
        except Exception as e:  # extraction/match crash is itself a finding
            errors.append({"id": case["id"], "stage": "extract/match", "error": f"{type(e).__name__}: {e}"})
            confusion[(expected, "(crash)")] += 1
            per_solver[expected]["support"] += 1
            continue

        selected = matches[0].solver.name if matches else "(none)"
        top_score = matches[0].score if matches else None
        gap = (matches[0].score - matches[1].score) if len(matches) > 1 else None

        confusion[(expected, selected)] += 1
        per_solver[expected]["support"] += 1
        per_solver[selected]["selected_total"] += 1
        if selected == expected:
            per_solver[expected]["correct"] += 1
        else:
            mismatches.append({
                "id": case["id"], "dataset": case["dataset"],
                "expected": expected, "selected": selected,
                "system_type": cp.system_type, "gap": gap,
                "problem": case["problem"][:90],
            })
        if gap is not None and gap <= gap_threshold:
            ambiguous.append({
                "id": case["id"], "expected": expected, "selected": selected,
                "top_score": top_score, "gap": gap,
                "runner_up": matches[1].solver.name,
                "correct": selected == expected,
                "problem": case["problem"][:90],
            })

        # numeric accuracy where gold value exists and routing found a solver
        if "expected_numeric" in case and matches:
            numeric["checked"] += 1
            try:
                out = matches[0].solver.solve(cp)
                actual = out.answer.numeric if (out.answer and out.answer.numeric is not None) else None
                tol = float(case["tolerance"])
                if actual is not None and math.isclose(float(actual), float(case["expected_numeric"]), rel_tol=tol, abs_tol=tol):
                    numeric["passed"] += 1
                else:
                    numeric["failures"].append({
                        "id": case["id"], "solver": selected,
                        "expected": case["expected_numeric"], "actual": actual,
                        "ok_claimed": bool(out.ok),
                    })
            except Exception as e:
                numeric["failures"].append({"id": case["id"], "solver": selected, "expected": case["expected_numeric"], "actual": None, "error": f"{type(e).__name__}: {e}"})

    # negative set: engine must NOT claim ok=True
    negative = {"checked": 0, "correct_refusals": 0, "false_positives": [], "crashes": []}
    for case in negative_cases:
        negative["checked"] += 1
        try:
            cp = extract_problem(case["problem"])
            matches = [m for s in registry.solvers if (m := s.match(cp))]
            matches.sort(key=lambda m: m.score, reverse=True)
            if not matches:
                negative["correct_refusals"] += 1
                continue
            out = matches[0].solver.solve(cp)
            if out.ok:
                negative["false_positives"].append({
                    "id": case["id"], "topic": case.get("topic"),
                    "solver": matches[0].solver.name,
                    "answer": out.answer.display if out.answer else None,
                    "problem": case["problem"][:90],
                })
            else:
                negative["correct_refusals"] += 1
        except Exception as e:
            negative["crashes"].append({"id": case["id"], "error": f"{type(e).__name__}: {e}"})

    perturbation = run_perturbation_probe(registry, routing_cases, limit)
    verification = run_verification_probe(registry, routing_cases, limit)
    provenance = run_provenance_probe(registry, routing_cases, limit)
    clarify = run_clarify_probe(registry, routing_cases, negative_cases, limit)

    duration = time.time() - t0

    total = sum(confusion.values())
    correct = sum(n for (e, s), n in confusion.items() if e == s)
    solver_rows = []
    for name, st in sorted(per_solver.items()):
        precision = st["correct"] / st["selected_total"] if st["selected_total"] else None
        recall = st["correct"] / st["support"] if st["support"] else None
        solver_rows.append({
            "solver": name, "support": st["support"], "selected_total": st["selected_total"],
            "correct": st["correct"],
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
        })
    top_pairs = [
        {"expected": e, "selected": s, "count": n}
        for (e, s), n in confusion.most_common() if e != s
    ][:15]

    return {
        "meta": {
            "units_backend": UNITS_BACKEND,
            "routing_cases": total,
            "negative_cases": negative["checked"],
            "gap_threshold": gap_threshold,
            "duration_seconds": round(duration, 2),
        },
        "routing": {
            "total": total, "correct": correct,
            "accuracy": round(correct / total, 4) if total else None,
            "top_confusion_pairs": top_pairs,
            "mismatches": mismatches,
        },
        "per_solver": solver_rows,
        "ambiguous": sorted(ambiguous, key=lambda a: (a["gap"] if a["gap"] is not None else 999)),
        "numeric": {
            "checked": numeric["checked"], "passed": numeric["passed"],
            "accuracy": round(numeric["passed"] / numeric["checked"], 4) if numeric["checked"] else None,
            "failures": numeric["failures"],
        },
        "negative": negative,
        "perturbation": perturbation,
        "verification": verification,
        "provenance": provenance,
        "clarify": clarify,
        "errors": errors,
        "confusion_matrix": [
            {"expected": e, "selected": s, "count": n} for (e, s), n in sorted(confusion.items())
        ],
    }


# ---------------------------------------------------------------- report
def to_markdown(r: dict) -> str:
    m, rt, nm, ng = r["meta"], r["routing"], r["numeric"], r["negative"]
    lines = [
        "# Routing Confusion & Accuracy Report",
        "",
        f"- units backend: **{m['units_backend']}**" + (" _(shim: 정식 pint 환경에서 재실행 권장)_" if m["units_backend"] == "shim" else ""),
        f"- routing cases: {m['routing_cases']} · negative cases: {m['negative_cases']} · duration: {m['duration_seconds']}s",
        "",
        "## 핵심 지표",
        "",
        f"| 지표 | 값 |",
        f"|---|---|",
        f"| Routing 정확도 (올바른 solver 선택) | **{rt['accuracy']:.1%}** ({rt['correct']}/{rt['total']}) |",
        f"| 수치 정답률 (gold 수치 보유 문항) | **{(nm['accuracy'] if nm['accuracy'] is not None else 0):.1%}** ({nm['passed']}/{nm['checked']}) |",
        f"| Negative 거절률 (못 푸는 문제를 거절) | **{(ng['correct_refusals']/ng['checked'] if ng['checked'] else 0):.1%}** ({ng['correct_refusals']}/{ng['checked']}) |",
        f"| 모호 케이스 (top1-top2 ≤ {m['gap_threshold']}) | {len(r['ambiguous'])} |",
        "",
        "## 상위 혼동 쌍 (재설계 우선순위)",
        "",
        "| expected → selected | count |",
        "|---|---|",
    ]
    for p in rt["top_confusion_pairs"]:
        lines.append(f"| `{p['expected']}` → `{p['selected']}` | {p['count']} |")
    if not rt["top_confusion_pairs"]:
        lines.append("| (혼동 없음) | - |")

    lines += ["", "## Solver별 precision / recall", "", "| solver | support | recall | precision |", "|---|---|---|---|"]
    for row in r["per_solver"]:
        if row["support"] == 0 and row["selected_total"] == 0:
            continue
        rec = f"{row['recall']:.0%}" if row["recall"] is not None else "-"
        prec = f"{row['precision']:.0%}" if row["precision"] is not None else "-"
        flag = " ⚠" if (row["recall"] is not None and row["recall"] < 0.9) or (row["precision"] is not None and row["precision"] < 0.9) else ""
        lines.append(f"| `{row['solver']}`{flag} | {row['support']} | {rec} | {prec} |")

    lines += ["", f"## 모호 케이스 (gap ≤ {m['gap_threshold']}) — '되묻기' 후보", ""]
    if r["ambiguous"]:
        lines += ["| id | gap | selected vs runner-up | 맞음? |", "|---|---|---|---|"]
        for a in r["ambiguous"][:20]:
            lines.append(f"| {a['id']} | {a['gap']} | `{a['selected']}` vs `{a['runner_up']}` | {'O' if a['correct'] else '**X**'} |")
        if len(r["ambiguous"]) > 20:
            lines.append(f"| … | | 외 {len(r['ambiguous'])-20}건 (JSON 참고) | |")
    else:
        lines.append("없음 — 현재 선택은 점수 격차가 충분히 큼.")

    lines += ["", "## 수치 오답", ""]
    if nm["failures"]:
        lines += ["| id | solver | expected | actual |", "|---|---|---|---|"]
        for f in nm["failures"][:20]:
            lines.append(f"| {f['id']} | `{f['solver']}` | {f['expected']} | {f.get('actual')}{' (crash: '+f['error']+')' if f.get('error') else ''} |")
        if len(nm["failures"]) > 20:
            lines.append(f"| … | 외 {len(nm['failures'])-20}건 | | |")
    else:
        lines.append(f"없음 — gold 수치 {nm['checked']}문항 전부 tolerance 내 일치.")

    lines += ["", "## Negative false-positive (환각성 오탐)", ""]
    if ng["false_positives"]:
        lines += ["| id | topic | solver가 주장한 답 |", "|---|---|---|"]
        for f in ng["false_positives"][:20]:
            lines.append(f"| {f['id']} | {f['topic']} | `{f['solver']}`: {f['answer']} |")
    else:
        lines.append(f"없음 — negative {ng['checked']}문항 전부 올바르게 거절.")
    if ng["crashes"]:
        lines += ["", f"negative 처리 중 crash {len(ng['crashes'])}건 — JSON 참고 (crash도 '거절'이 아니라 버그입니다)."]

    if r["errors"]:
        lines += ["", f"## 추출/매칭 crash {len(r['errors'])}건", ""]
        for e in r["errors"][:10]:
            lines.append(f"- {e['id']}: {e['error']}")


    vp = r.get("verification")
    if vp:
        t = vp["totals"]
        fp_rate = t["fp"] / t["n"] if t["n"] else 0
        lines += ["", "## 검증 스위트 — 무고 오탐 & 오염 검출률(mutation sensitivity)", "",
                  f"- 검증 대상(정답 결과): {t['n']} · 역대입 커버 {t['covered']} ({t['covered']/max(t['n'],1):.0%})",
                  f"- **무고 오탐(FP): {t['fp']}** ({fp_rate:.1%}) — 0이어야 함",
                  f"- 오염 검출률: ×1.1 → **{t['x1.1']}/{t['n']}** ({t['x1.1']/max(t['n'],1):.0%}) · 부호반전 → {t['sign']}/{t['n']} ({t['sign']/max(t['n'],1):.0%}) · 단위교란 → {t['unit']}/{t['n']} ({t['unit']/max(t['n'],1):.0%})",
                  "", "| system_type | n | 역대입 커버 | FP | ×1.1 검출 | 부호 검출 | 단위 검출 |", "|---|---|---|---|---|---|---|"]
        for st, rec in vp["per_type"].items():
            lines.append(f"| `{st}` | {rec['n']} | {rec['covered']} | {rec['fp']} | {rec['x1.1']} | {rec['sign']} | {rec['unit']} |")
        if vp["fp_examples"]:
            lines += ["", "무고 오탐 예시(수정 필요):", ""]
            for e in vp["fp_examples"]:
                lines.append(f"- `{e['type']}`: {e['errors']} — {e['problem']}")
        if vp["escape_examples"]:
            lines += ["", "역대입 커버인데 ×1.1을 놓친 예시(검사 강화 후보):", ""]
            for e in vp["escape_examples"]:
                lines.append(f"- `{e['type']}`: {e['problem']}")

    cl = r.get("clarify")
    if cl:
        lines += ["", "## 되묻기(clarification) 라우터", "",
                  f"- 벤치마크 오발동(FP): **{len(cl['fp'])}** (풀리는 문제를 질문으로 막은 횟수 — 0이어야 함)",
                  f"- 제작 모호 세트: 발동 {cl['crafted_fired']}/{len(cl['crafted'])} · 규칙 일치 {cl['crafted_rule_ok']} · 해소 성공 {cl['crafted_resolved']}/{cl['crafted_resolvable']}",
                  f"- negative 60건 중 질문 전환: {cl['negatives_with_clarification']} (거절 → 선택지 있는 대화)",
                  "", "| 문제 | 기대 규칙 | 발동 규칙 | 해소 |", "|---|---|---|---|"]
        for c in cl["crafted"]:
            lines.append(f"| {c['problem']} | {c['expected']} | {c['fired']} | {c['resolved'] if c['resolved'] is not None else '-'} |")

    pv = r.get("provenance")
    if pv:
        det_rate = pv["detected_total"] / pv["landed_total"] if pv["landed_total"] else 1.0
        lines += ["", "## 출처(provenance) — 배경 문장 주입 검출", "",
                  f"- 클린 텍스트 무고 플래그: **{pv['clean_fp']}** (0이어야 함)",
                  f"- 주입 성사 {pv['landed_total']}건 중 검출 **{pv['detected_total']}** ({det_rate:.0%})",
                  "", "| 주입 문장 | 성사 | 검출 | 답 보류(사용 심볼) | 답 유지+경고(미사용) |", "|---|---|---|---|---|"]
        for it in pv["injectors"]:
            lines.append(f"| {it['name']} | {it['landed']} | {it['detected']} | {it['withheld_error']} | {it['kept_with_warning']} |")
        misses = [m for it in pv["injectors"] for m in it["missed_examples"]]
        if misses:
            lines += ["", "미검출 예시:", ""]
            for m in misses[:6]:
                lines.append(f"- {m['id']}: {m['missed']}")

    pb = r.get("perturbation")
    if pb:
        lines += ["", "## 교란(perturbation) 강건성 — 라벨 보존 변형 후 불변량 유지", "",
                  "| 변형 | 적용 | routing 깨짐 | outputs 표류 | 수치 깨짐 | 파손율 |", "|---|---|---|---|---|---|"]
        for tr in pb["transforms"]:
            rate = f"{tr['break_rate']:.1%}" if tr["break_rate"] is not None else "-"
            broken_any = tr["routing_broken"] + tr["outputs_drift"] + tr["numeric_broken"]
            flag = " ⚠" if broken_any else ""
            lines.append(f"| {tr['name']}{flag} | {tr['applied']} | {tr['routing_broken']} | {tr['outputs_drift']} | {tr['numeric_broken']} | {rate} |")
        broken_examples = [e for tr in pb["transforms"] for e in tr["examples"]]
        if broken_examples:
            lines += ["", "깨진 예시:", ""]
            for e in broken_examples[:14]:
                lines.append(f"- [{e['kind']}] {e['id']}: {e['detail']}  \n  ↳ {e['mutated']}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gap", type=int, default=8, help="ambiguity threshold for top1-top2 score gap")
    ap.add_argument("--limit", type=int, default=None, help="limit cases for a quick pass")
    ap.add_argument("--out", type=Path, default=BACKEND / "reports" / "routing_confusion")
    args = ap.parse_args()

    result = run(args.gap, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "report.md").write_text(to_markdown(result), encoding="utf-8")

    rt, nm, ng = result["routing"], result["numeric"], result["negative"]
    print(f"[routing-confusion] backend={result['meta']['units_backend']} cases={rt['total']}")
    print(f"  routing accuracy : {rt['accuracy']:.1%} ({rt['correct']}/{rt['total']})")
    if nm["checked"]:
        print(f"  numeric accuracy : {nm['accuracy']:.1%} ({nm['passed']}/{nm['checked']})")
    if ng["checked"]:
        print(f"  negative refusal : {ng['correct_refusals']}/{ng['checked']} (false-positive {len(ng['false_positives'])}, crash {len(ng['crashes'])})")
    print(f"  ambiguous (gap<={result['meta']['gap_threshold']}): {len(result['ambiguous'])}")
    pb = result.get("perturbation")
    if pb:
        worst = max(pb["transforms"], key=lambda t: (t["routing_broken"] + t["outputs_drift"] + t["numeric_broken"]))
        wb = worst["routing_broken"] + worst["outputs_drift"] + worst["numeric_broken"]
        print(f"  perturbation     : {pb['total_breaks']} breaks across {len(pb['transforms'])} transforms (worst: {worst['name']} = {wb})")
    vp = result.get("verification")
    if vp:
        t = vp["totals"]
        print(f"  verification     : FP {t['fp']}/{t['n']} | sens x1.1 {t['x1.1']}/{t['n']}, sign {t['sign']}/{t['n']}, unit {t['unit']}/{t['n']} | resid-cov {t['covered']}/{t['n']}")
    cl = result.get("clarify")
    if cl:
        print(f"  clarify          : FP {len(cl['fp'])} | crafted fired {cl['crafted_fired']}/{len(cl['crafted'])} rule-ok {cl['crafted_rule_ok']} resolved {cl['crafted_resolved']}/{cl['crafted_resolvable']} | negatives→질문 {cl['negatives_with_clarification']}/{cl['negatives_total']}")
    pv = result.get("provenance")
    if pv:
        dr = pv["detected_total"] / pv["landed_total"] if pv["landed_total"] else 1.0
        print(f"  provenance       : clean-FP {pv['clean_fp']} | injected {pv['landed_total']} detected {pv['detected_total']} ({dr:.0%})")
    print(f"  report: {args.out / 'report.md'}")


if __name__ == "__main__":
    main()
