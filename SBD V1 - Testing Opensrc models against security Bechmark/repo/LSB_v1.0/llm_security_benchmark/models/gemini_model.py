"""Google Gemini model connector."""

from typing import List, Optional
import google.generativeai as genai
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


class GeminiModel(BaseModel):
    """Connector for Google Gemini models."""

    def __init__(self, model_name: str, model_id: str, api_key: str, **kwargs):
        """Initialize Gemini model connector."""
        super().__init__(model_name, model_id, api_key, **kwargs)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_id)

    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code using Gemini API.
        
        Args:
            prompt: Input prompt
            num_samples: Number of samples to generate
            **kwargs: Additional parameters
            
        Returns:
            List of ModelResponse objects
        """
        responses = []
        
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                top_p=kwargs.get("top_p", 0.95),
            )
            
            # Gemini doesn't support num_samples, so we generate sequentially
            for _ in range(num_samples):
                start_time = time.time()
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config,
                )
                
                elapsed_time = (time.time() - start_time) * 1000
                
                # Extract token count if available
                tokens = 0
                if hasattr(response, 'usage_metadata'):
                    tokens = response.usage_metadata.output_token_count
                
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=response.text if response.text else "",
                    tokens_used=tokens,
                    latency_ms=elapsed_time,
                    temperature=self.temperature,
                    confidence_score=None,
                    raw_response=None
                )
                responses.append(model_response)
                
                self.total_tokens += tokens
            
            self.request_count += 1
            
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            raise
        
        return responses

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        response = self.model.generate_content(prompt)
        return response.text
