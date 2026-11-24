"""Mistral model connector (HTTP OpenAI-compatible API)."""

from __future__ import annotations

import logging
import time
from typing import List

import requests

from .base_model import BaseModel, ModelResponse

logger = logging.getLogger(__name__)

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"


class MistralModel(BaseModel):
    """Connector for Mistral AI chat models via REST."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.api_key = api_key
        self.timeout_sec = float(kwargs.get("timeout_sec") or 90.0)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs,
    ) -> List[ModelResponse]:
        responses: List[ModelResponse] = []
        max_tokens = int(kwargs.get("max_tokens") or self.max_tokens or 2048)
        temperature = float(kwargs.get("temperature", self.temperature))
        try:
            for _ in range(max(1, num_samples)):
                start = time.time()
                text, tokens = self._chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                elapsed_ms = (time.time() - start) * 1000.0
                responses.append(
                    ModelResponse(
                        model_name=self.model_name,
                        prompt=prompt,
                        response=text,
                        tokens_used=tokens,
                        latency_ms=elapsed_ms,
                        temperature=temperature,
                        confidence_score=None,
                        raw_response=None,
                    )
                )
                self.total_tokens += tokens
            self.request_count += 1
        except Exception as err:
            logger.error("Error calling Mistral API: %s", err)
            raise
        return responses

    def _chat(
        self,
        messages: List[dict],
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_err: Exception | None = None
        for attempt in range(1, 6):
            resp = requests.post(
                MISTRAL_CHAT_URL,
                headers=headers,
                json=payload,
                timeout=self.timeout_sec,
            )
            if resp.status_code in (429, 503):
                retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                delay = 60.0
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = 60.0
                delay = min(max(delay, 15.0), 180.0)
                last_err = RuntimeError(
                    f"Mistral HTTP {resp.status_code} rate limit try again in {delay:.1f}s: {resp.text[:300]}"
                )
                logger.warning("Mistral backoff %.0fs (attempt %s): %s", delay, attempt, str(last_err)[:180])
                time.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"Mistral HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return "", 0
            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()
            usage = data.get("usage") or {}
            tokens = int(usage.get("total_tokens") or 0)
            return text, tokens
        raise last_err or RuntimeError("Mistral rate-limited after retries")

    def _call_api(self, prompt: str) -> str:
        text, _ = self._chat(
            [{"role": "user", "content": prompt}],
            max_tokens=int(self.max_tokens or 2048),
            temperature=float(self.temperature or 0.0),
        )
        return text
