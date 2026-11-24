"""Groq model connector."""

from typing import List
from groq import Groq
from .base_model import BaseModel, ModelResponse
import time
import logging
import re

logger = logging.getLogger(__name__)

THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.reasoning = None
        self.reasoning_content = None


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeUsage:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class GroqModel(BaseModel):
    """Connector for Groq models (Llama, etc)."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize Groq model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.client = Groq(api_key=api_key)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate using Groq Chat Completions API."""
        responses = []
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        try:
            for _ in range(num_samples):
                start_time = time.time()
                request = self._build_request(prompt, max_tokens, temperature, kwargs)
                chat_completion = self._create(request, max_tokens)
                elapsed_time = (time.time() - start_time) * 1000
                choice = chat_completion.choices[0]
                response_text = self._extract_text(choice)
                usage = chat_completion.usage
                tokens = getattr(usage, "total_tokens", None) or getattr(usage, "completion_tokens", 0) or 0

                responses.append(ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=response_text,
                    tokens_used=tokens,
                    latency_ms=elapsed_time,
                    temperature=temperature,
                    confidence_score=None,
                    raw_response={
                        "input_tokens": getattr(usage, "prompt_tokens", 0),
                        "output_tokens": getattr(usage, "completion_tokens", 0),
                    }
                ))
                self.total_tokens += tokens

            self.request_count += 1
        except Exception as e:
            logger.error(f"Error calling Groq API: {str(e)}")
            raise

        return responses

    def _build_request(self, prompt: str, max_tokens: int, temperature: float, kwargs: dict) -> dict:
        request = {
            "messages": [{"role": "user", "content": prompt}],
            "model": self.model_id,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if "top_p" in kwargs:
            request["top_p"] = kwargs["top_p"]
        model_id = self.model_id.lower()
        if "gpt-oss" in model_id:
            request["reasoning_effort"] = "low"
            request["max_completion_tokens"] = max(max_tokens, 256)
        elif "qwen" in model_id:
            request["reasoning_effort"] = "none"
        request["tool_choice"] = "none"
        return request

    def _create(self, request: dict, max_tokens: int):
        try:
            return self.client.chat.completions.create(**request)
        except Exception as first_err:
            message = str(first_err).lower()
            if "tool_use_failed" in message or "tool choice is none" in message:
                text = self._extract_failed_generation(str(first_err))
                if text:
                    return _FakeCompletion(text)
            if "reasoning_effort" in message:
                request.pop("reasoning_effort", None)
                return self.client.chat.completions.create(**request)
            if "max_completion_tokens" in message or "max_tokens" in message:
                request.pop("max_completion_tokens", None)
                request["max_tokens"] = max_tokens
                return self.client.chat.completions.create(**request)
            raise

    @staticmethod
    def _extract_failed_generation(error_text: str) -> str:
        match = re.search(r"(?:def |import |from )[\s\S]+", error_text)
        if not match:
            return ""
        text = match.group(0)
        text = re.sub(r"['\"]\}\}+.*$", "", text).strip()
        return text.rstrip("'\"} ")

    @staticmethod
    def _extract_text(choice) -> str:
        message = choice.message
        text = (getattr(message, "content", None) or "").strip()
        if not text:
            text = (getattr(message, "reasoning", None) or "").strip()
        if not text:
            for item in getattr(message, "reasoning_content", None) or []:
                if isinstance(item, str):
                    text += item
                elif getattr(item, "text", None):
                    text += item.text
            text = text.strip()
        text = THINK_RE.sub("", text).strip()
        return text

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        responses = self.generate(prompt, num_samples=1)
        return responses[0].response
