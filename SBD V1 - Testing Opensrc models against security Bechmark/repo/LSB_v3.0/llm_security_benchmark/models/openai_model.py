"""OpenAI model connector."""

from typing import List, Optional
import openai
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class OpenAIModel(BaseModel):
    """Connector for OpenAI API models (GPT-3.5, GPT-4, etc)."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize OpenAI model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        openai.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code using OpenAI API.
        
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
                n=num_samples,
                top_p=kwargs.get("top_p", 0.95),
            )
            
            elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
            
            for choice in response.choices:
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=choice.message.content,
                    tokens_used=response.usage.total_tokens // num_samples,
                    latency_ms=elapsed_time / num_samples,
                    temperature=self.temperature,
                    confidence_score=None,  # OpenAI doesn't provide confidence
                    raw_response=response.model_dump()
                )
                responses.append(model_response)
            
            self.request_count += 1
            self.total_tokens += response.usage.total_tokens
            
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {str(e)}")
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
