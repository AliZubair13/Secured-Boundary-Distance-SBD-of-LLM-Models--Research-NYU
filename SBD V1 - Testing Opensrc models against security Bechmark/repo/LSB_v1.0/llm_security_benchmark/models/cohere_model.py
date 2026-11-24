"""Cohere model connector."""

from typing import List, Optional
import cohere
import time
import logging
from .base_model import BaseModel, ModelResponse

logger = logging.getLogger(__name__)


class CohereModel(BaseModel):
    """Connector for Cohere API."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.client = cohere.Client(api_key)

    def generate(self, prompt: str, num_samples: int = 1, **kwargs) -> List[ModelResponse]:
        responses = []
        try:
            start_time = time.time()
            result = self.client.generate(
                model=self.model_id,
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                k=num_samples,
            )
            elapsed = (time.time() - start_time) * 1000
            # Cohere returns a list of generations
            for gen in result.generations:
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=gen.text,
                    tokens_used=0,
                    latency_ms=elapsed / max(1, len(result.generations)),
                    temperature=self.temperature,
                    confidence_score=None,
                    raw_response=None
                )
                responses.append(model_response)
            self.request_count += 1
        except Exception as e:
            logger.error(f"Cohere API error: {e}")
            raise
        return responses

    def _call_api(self, prompt: str) -> str:
        res = self.client.generate(model=self.model_id, prompt=prompt, max_tokens=self.max_tokens)
        return res.generations[0].text
