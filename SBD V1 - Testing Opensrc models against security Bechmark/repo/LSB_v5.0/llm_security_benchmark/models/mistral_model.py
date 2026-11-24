"""Mistral model connector."""

from typing import List, Optional
from mistralai.client import MistralClient
from mistralai.models.chat_message import ChatMessage
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class MistralModel(BaseModel):
    """Connector for Mistral AI models."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize Mistral model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        self.client = MistralClient(api_key=api_key)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code using Mistral API.
        
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
            
            message = ChatMessage(role="user", content=prompt)
            
            chat_response = self.client.chat(
                model=self.model_id,
                messages=[message],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=kwargs.get("top_p", 0.95),
            )
            
            elapsed_time = (time.time() - start_time) * 1000
            
            # Extract response
            response_text = chat_response.choices[0].message.content
            
            # Mistral doesn't support multiple samples in single call
            # So we return the single response, can be called multiple times
            model_response = ModelResponse(
                model_name=self.model_name,
                prompt=prompt,
                response=response_text,
                tokens_used=0,  # Mistral API doesn't provide detailed token count
                latency_ms=elapsed_time,
                temperature=self.temperature,
                confidence_score=None,
                raw_response=None
            )
            responses.append(model_response)
            
            self.request_count += 1
            
        except Exception as e:
            logger.error(f"Error calling Mistral API: {str(e)}")
            raise
        
        return responses

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        message = ChatMessage(role="user", content=prompt)
        chat_response = self.client.chat(
            model=self.model_id,
            messages=[message],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return chat_response.choices[0].message.content
