"""Cohere model connector."""

from typing import List
import cohere
import time
import logging
from .base_model import BaseModel, ModelResponse

logger = logging.getLogger(__name__)


class CohereModel(BaseModel):
    """Connector for Cohere Chat API."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        super().__init__(model_name, model_id, api_key, **kwargs)
        self._client_v2 = None
        self._client_v1 = None
        if hasattr(cohere, "ClientV2"):
            try:
                self._client_v2 = cohere.ClientV2(api_key)
            except Exception:
                self._client_v2 = None
        self._client_v1 = cohere.Client(api_key)

    def generate(self, prompt: str, num_samples: int = 1, **kwargs) -> List[ModelResponse]:
        responses = []
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)
        try:
            for _ in range(num_samples):
                start_time = time.time()
                text, tokens = self._chat(prompt, max_tokens, temperature)
                elapsed = (time.time() - start_time) * 1000
                responses.append(ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=text,
                    tokens_used=tokens,
                    latency_ms=elapsed,
                    temperature=temperature,
                    confidence_score=None,
                    raw_response=None,
                ))
                self.total_tokens += tokens
            self.request_count += 1
        except Exception as e:
            logger.error(f"Cohere API error: {e}")
            raise
        return responses

    def _chat(self, prompt: str, max_tokens: int, temperature: float):
        if self._client_v2 is not None:
            result = self._client_v2.chat(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = ""
            message = getattr(result, "message", None)
            if message is not None:
                content = getattr(message, "content", None) or []
                parts = []
                for part in content:
                    if getattr(part, "text", None):
                        parts.append(part.text)
                    elif isinstance(part, dict) and part.get("text"):
                        parts.append(part["text"])
                text = "\n".join(parts).strip()
            if not text:
                text = (getattr(result, "text", None) or "").strip()
            tokens = 0
            usage = getattr(result, "usage", None)
            if usage is not None:
                billed = getattr(usage, "billed_units", None) or getattr(usage, "tokens", None)
                if billed is not None:
                    tokens = (
                        getattr(billed, "input_tokens", 0) or 0
                    ) + (
                        getattr(billed, "output_tokens", 0) or 0
                    )
            return text, tokens

        result = self._client_v1.chat(
            model=self.model_id,
            message=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (getattr(result, "text", None) or "").strip()
        tokens = 0
        meta = getattr(result, "meta", None)
        billed = getattr(meta, "billed_units", None) if meta is not None else None
        if billed is not None:
            tokens = (getattr(billed, "input_tokens", 0) or 0) + (getattr(billed, "output_tokens", 0) or 0)
        return text, tokens

    def _call_api(self, prompt: str) -> str:
        text, _ = self._chat(prompt, self.max_tokens, self.temperature)
        return text
