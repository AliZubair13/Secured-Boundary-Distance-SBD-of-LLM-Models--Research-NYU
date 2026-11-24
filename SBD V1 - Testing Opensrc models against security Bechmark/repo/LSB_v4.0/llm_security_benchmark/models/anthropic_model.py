"""Anthropic Claude model connector."""

from typing import List, Optional
from anthropic import Anthropic
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class AnthropicModel(BaseModel):
    """Connector for Anthropic Claude models."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize Anthropic model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.client = Anthropic(api_key=api_key)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code using Anthropic API.
        
        Args:
            prompt: Input prompt
            num_samples: Number of samples to generate
            **kwargs: Additional parameters
            
        Returns:
            List of ModelResponse objects
        """
        responses = []
        
        try:
            for _ in range(num_samples):
                start_time = time.time()
                
                message = self.client.messages.create(
                    model=self.model_id,
                    max_tokens=self.max_tokens,
                    system="You are an expert programmer. Generate secure, production-ready code.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                )
                
                elapsed_time = (time.time() - start_time) * 1000
                
                response_text = message.content[0].text
                
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=response_text,
                    tokens_used=message.usage.output_tokens,
                    latency_ms=elapsed_time,
                    temperature=self.temperature,
                    confidence_score=None,
                    raw_response={
                        "input_tokens": message.usage.input_tokens,
                        "output_tokens": message.usage.output_tokens,
                    }
                )
                responses.append(model_response)
                
                self.total_tokens += message.usage.output_tokens
            
            self.request_count += 1
            
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {str(e)}")
            raise
        
        return responses

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        message = self.client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
        )
        return message.content[0].text
