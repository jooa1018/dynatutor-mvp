from __future__ import annotations

from app.schemas.llm import AIExplainResponse, LLMStatusResponse
from engine.llm.client import LLMClientError, TutorLLMClient, get_llm_config
from engine.llm.guardrails import build_locked_facts, validate_llm_explanation
from engine.llm.prompt import build_llm_prompt
from engine.llm.template import build_fallback_explanation, append_final_check_if_needed
from engine.services import solve_problem


def llm_status() -> LLMStatusResponse:
    cfg = get_llm_config()
    return LLMStatusResponse(
        enabled=cfg.enabled,
        provider=cfg.provider,
        model=cfg.model,
        reason=cfg.reason,
        base_url=cfg.base_url if cfg.provider != "openai" else None,
    )


def explain_with_optional_llm(problem_text: str, student_solution: str | None, level: str, style: str, force_template: bool = False) -> AIExplainResponse:
    solution = solve_problem(problem_text, student_solution)
    locked = build_locked_facts(solution)
    fallback = append_final_check_if_needed(build_fallback_explanation(solution, locked, level), locked)
    prompt = build_llm_prompt(problem_text, student_solution, solution, locked, level, style)
    cfg = get_llm_config()

    if force_template or not cfg.enabled:
        reason = cfg.reason or "force_template=True" if force_template else cfg.reason
        return AIExplainResponse(
            ok=True,
            used_llm=False,
            provider=cfg.provider,
            model=cfg.model,
            explanation=fallback,
            fallback_explanation=fallback,
            locked_facts=locked,
            integrity_passed=True,
            integrity_warnings=[reason] if reason else [],
            integrity_report={"mode": "template", "locked_hash": locked.locked_hash},
            displayed_source="template",
            prompt_preview=prompt,
            raw_usage=None,
        )

    try:
        result = TutorLLMClient(cfg).generate(prompt)
        integrity = validate_llm_explanation(result.text, locked)
        # If guardrail fails, keep the LLM text out of the user-facing explanation and show fallback.
        explanation = result.text if integrity.passed else fallback
        warnings = list(integrity.warnings)
        displayed_source = "llm" if integrity.passed else "template_fallback_after_guardrail"
        if not integrity.passed:
            warnings.append("안전 검사를 통과하지 못해 사용자 표시 설명은 템플릿 설명으로 대체했습니다.")
        return AIExplainResponse(
            ok=True,
            used_llm=integrity.passed,
            provider=result.provider,
            model=result.model,
            explanation=explanation,
            fallback_explanation=fallback,
            locked_facts=locked,
            integrity_passed=integrity.passed,
            integrity_warnings=warnings,
            integrity_report=integrity.report,
            displayed_source=displayed_source,
            prompt_preview=prompt,
            raw_usage=result.usage,
        )
    except LLMClientError as e:
        return AIExplainResponse(
            ok=True,
            used_llm=False,
            provider=cfg.provider,
            model=cfg.model,
            explanation=fallback,
            fallback_explanation=fallback,
            locked_facts=locked,
            integrity_passed=True,
            integrity_warnings=[str(e), "LLM 호출 실패로 템플릿 설명을 표시했습니다."],
            integrity_report={"mode": "llm_error_template_fallback", "locked_hash": locked.locked_hash},
            displayed_source="template_fallback_after_error",
            prompt_preview=prompt,
            raw_usage=None,
        )
