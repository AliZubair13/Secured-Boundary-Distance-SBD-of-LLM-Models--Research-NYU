"""XAI Grok model connector."""

from typing import List, Optional
from openai import OpenAI
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class XAIModel(BaseModel):
    """Connector for XAI Grok models (uses OpenAI-compatible API)."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize XAI Grok model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code using XAI Grok API.
        
        Args:
            prompt: Input prompt
            num_samples: Number of samples to generate
            **kwargs: Additional parameters
            
        Returns:
            List of ModelResponse objects
        """
        responses = []
        
        try:
            start_time = time.time()
            
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert programmer. Generate secure, production-ready code."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=kwargs.get("top_p", 0.95),
                n=num_samples,
            )
            
            elapsed_time = (time.time() - start_time) * 1000
            
            for choice in response.choices:
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=choice.message.content,
                    tokens_used=response.usage.total_tokens // num_samples,
                    latency_ms=elapsed_time / num_samples,
                    temperature=self.temperature,
                    confidence_score=None,
                    raw_response=None
                )
                responses.append(model_response)
            
            self.request_count += 1
            self.total_tokens += response.usage.total_tokens
            
        except Exception as e:
            logger.error(f"Error calling XAI API: {str(e)}")
            raise
        
        return responses

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content
