"""Groq model connector."""

from typing import List, Optional
from groq import Groq
from .base_model import BaseModel, ModelResponse
import time
import logging

logger = logging.getLogger(__name__)


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
        """Generate code using Groq API.
        
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
                
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert programmer. Generate secure, production-ready code."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=self.model_id,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=kwargs.get("top_p", 0.95),
                )
                
                elapsed_time = (time.time() - start_time) * 1000
                
                response_text = chat_completion.choices[0].message.content
                tokens = chat_completion.usage.completion_tokens
                
                model_response = ModelResponse(
                    model_name=self.model_name,
                    prompt=prompt,
                    response=response_text,
                    tokens_used=tokens,
                    latency_ms=elapsed_time,
                    temperature=self.temperature,
                    confidence_score=None,
                    raw_response={
                        "input_tokens": chat_completion.usage.prompt_tokens,
                        "output_tokens": chat_completion.usage.completion_tokens,
                    }
                )
                responses.append(model_response)
                
                self.total_tokens += tokens
            
            self.request_count += 1
            
        except Exception as e:
            logger.error(f"Error calling Groq API: {str(e)}")
            raise
        
        return responses

    def _call_api(self, prompt: str) -> str:
        """Make single API call."""
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return chat_completion.choices[0].message.content
