"""Base model class for LLM connectors."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import json
import time


@dataclass
class ModelResponse:
    """Standard response format from any model."""
    model_name: str
    prompt: str
    response: str
    tokens_used: int
    latency_ms: float
    temperature: float
    confidence_score: Optional[float] = None
    raw_response: Optional[Dict] = None


class BaseModel(ABC):
    """Abstract base class for all LLM model connectors."""

    def __init__(
        self,
        model_name: str,
        model_id: str,
        api_key: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ):
        """Initialize base model.
        
        Args:
            model_name: Human-readable name
            model_id: API model identifier
            api_key: API key for authentication
            temperature: Sampling temperature
            max_tokens: Max tokens in response
        """
        self.model_name = model_name
        self.model_id = model_id
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_config = kwargs
        self.request_count = 0
        self.total_tokens = 0

    @abstractmethod
    def generate(
        self,
        prompt: str,
        num_samples: int = 1,
        **kwargs
    ) -> List[ModelResponse]:
        """Generate code given a prompt.
        
        Args:
            prompt: Input prompt
            num_samples: Number of samples to generate
            **kwargs: Additional model-specific parameters
            
        Returns:
            List of ModelResponse objects
        """
        pass

    @abstractmethod
    def _call_api(self, prompt: str) -> str:
        """Make API call to model.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Model response string
        """
        pass

    def batch_generate(
        self,
        prompts: List[str],
        num_samples_per_prompt: int = 1,
        parallel: bool = False
    ) -> List[List[ModelResponse]]:
        """Generate for multiple prompts.
        
        Args:
            prompts: List of input prompts
            num_samples_per_prompt: Samples per prompt
            parallel: Whether to use parallel requests
            
        Returns:
            List of lists of ModelResponse objects
        """
        results = []
        for prompt in prompts:
            responses = self.generate(prompt, num_samples_per_prompt)
            results.append(responses)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get model usage statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            "model_name": self.model_name,
            "total_requests": self.request_count,
            "total_tokens": self.total_tokens,
            "avg_tokens_per_request": (
                self.total_tokens / self.request_count
                if self.request_count > 0 else 0
            ),
        }

    def reset_stats(self):
        """Reset usage statistics."""
        self.request_count = 0
        self.total_tokens = 0
