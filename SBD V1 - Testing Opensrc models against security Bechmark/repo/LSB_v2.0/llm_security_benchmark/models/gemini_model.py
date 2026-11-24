"""Google Gemini model connector."""

from typing import List, Tuple
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class GeminiModel(BaseModel):
    """Connector for Google Gemini models."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize Gemini model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        self._client_v2 = None
        self._legacy_model = None
        self._use_v2 = False

        try:
            from google import genai
            self._client_v2 = genai.Client(api_key=api_key)
            self._use_v2 = True
        except Exception:
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=api_key)
            self._legacy_model = genai_legacy.GenerativeModel(model_id)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate using Gemini API with thinking disabled when possible."""
        responses = []
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        try:
            for _ in range(num_samples):
                start_time = time.time()
                if self._use_v2:
                    text, tokens = self._generate_v2(prompt, max_tokens, temperature)
                else:
                    text, tokens = self._generate_legacy(prompt, max_tokens, temperature)
                elapsed_time = (time.time() - start_time) * 1000
                responses.append(ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=text,
                    tokens_used=tokens,
                    latency_ms=elapsed_time,
                    temperature=temperature,
                    confidence_score=None,
                    raw_response=None,
                ))
                self.total_tokens += tokens
            self.request_count += 1
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            raise

        return responses

    def _generate_v2(self, prompt: str, max_tokens: int, temperature: float) -> Tuple[str, int]:
        from google.genai import types

        attempts = [
            {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "thinking_config": types.ThinkingConfig(thinking_budget=0),
            },
            {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        ]
        last_err = None
        for config_kwargs in attempts:
            try:
                response = self._client_v2.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                text = self._extract_text(response)
                tokens = self._extract_tokens(response)
                return text, tokens
            except Exception as err:
                last_err = err
                message = str(err).lower()
                if "thinking" in message or "invalid argument" in message or "invalid_argument" in message:
                    continue
                raise
        if last_err:
            raise last_err
        return "", 0

    @staticmethod
    def _extract_text(response) -> str:
        try:
            text = getattr(response, "text", None)
            if text:
                return text.strip()
        except Exception:
            pass
        chunks = []
        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    chunks.append(part_text)
        return "\n".join(chunks).strip()

    @staticmethod
    def _extract_tokens(response) -> int:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return 0
        return (
            getattr(usage, "total_token_count", 0)
            or getattr(usage, "candidates_token_count", 0)
            or 0
        )

    def _generate_legacy(self, prompt: str, max_tokens: int, temperature: float):
        import google.generativeai as genai_legacy

        generation_config = genai_legacy.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = self._legacy_model.generate_content(
            prompt,
            generation_config=generation_config,
        )
        text = ""
        try:
            text = (response.text or "").strip()
        except Exception:
            text = ""
        tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens = getattr(response.usage_metadata, "total_token_count", 0) or getattr(
                response.usage_metadata, "candidates_token_count", 0
            ) or 0
        return text, tokens

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        if self._use_v2:
            text, _ = self._generate_v2(prompt, self.max_tokens, self.temperature)
            return text
        text, _ = self._generate_legacy(prompt, self.max_tokens, self.temperature)
        return text
