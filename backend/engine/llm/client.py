from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMConfig:
    enabled: bool
    provider: str
    model: str | None
    api_key: str | None
    base_url: str
    timeout_seconds: float = 30.0
    reason: str | None = None


def get_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    enabled_raw = os.getenv("LLM_ENABLED", "auto").strip().lower()

    if enabled_raw in {"0", "false", "no", "off"}:
        return LLMConfig(False, provider, model, api_key, base_url, reason="LLM_ENABLED가 꺼져 있습니다.")
    if provider == "mock":
        return LLMConfig(True, provider, model or "mock-tutor", api_key, base_url)
    if enabled_raw in {"1", "true", "yes", "on"} and not api_key:
        return LLMConfig(False, provider, model, api_key, base_url, reason="API 키가 없습니다. OPENAI_API_KEY 또는 LLM_API_KEY를 설정하세요.")
    if enabled_raw == "auto" and not api_key:
        return LLMConfig(False, provider, model, api_key, base_url, reason="API 키가 없어 템플릿 설명 모드로 동작합니다.")
    return LLMConfig(True, provider, model, api_key, base_url)


@dataclass
class LLMCallResult:
    text: str
    usage: dict[str, Any] | None = None
    provider: str = "template"
    model: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClientError(RuntimeError):
    pass


class TutorLLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_llm_config()

    def generate(self, prompt: str) -> LLMCallResult:
        if not self.config.enabled:
            raise LLMClientError(self.config.reason or "LLM이 비활성화되어 있습니다.")
        if self.config.provider == "mock":
            return LLMCallResult(
                text=(
                    "### 한눈에 보기\n"
                    "이 설명은 mock LLM 모드에서 생성됐습니다. 실제 API 비용 없이 LLM 연결 흐름을 테스트합니다.\n\n"
                    "### 왜 이 식을 쓰는가\n"
                    "solver가 잠근 공식과 최종값만 사용해서 설명해야 합니다.\n\n"
                    "### 단계별 설명\n"
                    "1. 문제 유형을 먼저 확인합니다.\n2. 사용할 수 있는 식과 쓰면 안 되는 식을 나눕니다.\n3. 검산된 최종 답을 그대로 설명합니다.\n\n"
                    "### 실수 방지\n새로운 숫자나 조건을 만들면 안 됩니다.\n\n"
                    "### 마지막 확인\n최종 답은 solver 결과 카드에 표시된 값을 그대로 따릅니다."
                ),
                usage={"mode": "mock"},
                provider="mock",
                model=self.config.model,
            )
        if self.config.provider in {"openai", "openai-compatible", "compatible"}:
            return self._call_openai_responses(prompt)
        raise LLMClientError(f"지원하지 않는 LLM_PROVIDER입니다: {self.config.provider}")

    def _call_openai_responses(self, prompt: str) -> LLMCallResult:
        if not self.config.api_key:
            raise LLMClientError("API 키가 없습니다.")
        url = f"{self.config.base_url}/responses"
        payload = {
            "model": self.config.model,
            "input": prompt,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:1200]
            raise LLMClientError(f"LLM HTTP 오류 {e.code}: {detail}") from e
        except Exception as e:
            raise LLMClientError(f"LLM 호출 실패: {e}") from e

        text = self._extract_text(data)
        if not text:
            raise LLMClientError("LLM 응답에서 텍스트를 찾지 못했습니다.")
        usage = data.get("usage") if isinstance(data, dict) else None
        return LLMCallResult(text=text, usage=usage, provider=self.config.provider, model=self.config.model, raw=data)

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        chunks: list[str] = []
        for item in data.get("output", []) or []:
            for content in item.get("content", []) or []:
                if isinstance(content.get("text"), str):
                    chunks.append(content["text"])
        return "\n".join(chunks).strip()
