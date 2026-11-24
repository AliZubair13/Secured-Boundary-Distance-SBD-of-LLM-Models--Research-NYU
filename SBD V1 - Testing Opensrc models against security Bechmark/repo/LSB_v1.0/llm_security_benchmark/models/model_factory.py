"""Model factory for creating LLM connectors."""

import os
from typing import Dict, Any, Optional
from .base_model import BaseModel
from .openai_model import OpenAIModel
from .gemini_model import GeminiModel
from .mistral_model import MistralModel
from .anthropic_model import AnthropicModel
from .groq_model import GroqModel
from .xai_model import XAIModel


class ModelFactory:
    """Factory for creating model connectors."""

    PROVIDERS = {
        "openai": OpenAIModel,
        "google": GeminiModel,
        "gemini": GeminiModel,
        "mistral": MistralModel,
        "anthropic": AnthropicModel,
        "groq": GroqModel,
        "xai": XAIModel,
        "grok": XAIModel,
        "cohere": CohereModel,
    }

    @staticmethod
    def create_model(
        provider: str,
        model_name: str,
        model_id: str,
        api_key: Optional[str] = None,
        **config
    ) -> BaseModel:
        """Create a model connector instance.
        
        Args:
            provider: Provider name (openai, google, mistral, etc)
            model_name: Human-readable model name
            model_id: Model identifier for API
            api_key: API key (if None, read from env)
            **config: Additional configuration
            
        Returns:
            Initialized BaseModel subclass instance
            
        Raises:
            ValueError: If provider not supported
            RuntimeError: If API key not found
        """
        provider = provider.lower()
        
        if provider not in ModelFactory.PROVIDERS:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported: {list(ModelFactory.PROVIDERS.keys())}"
            )
        
        # Get API key from parameter or environment
        if api_key is None:
            env_var_map = {
                "openai": "OPENAI_API_KEY",
                "google": "GOOGLE_API_KEY",
                "gemini": "GOOGLE_API_KEY",
                "mistral": "MISTRAL_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "groq": "GROQ_API_KEY",
                "xai": "XAI_API_KEY",
                "grok": "XAI_API_KEY",
            }
            env_var = env_var_map.get(provider)
            api_key = os.getenv(env_var)
            
            if not api_key:
                raise RuntimeError(
                    f"API key for {provider} not provided and "
                    f"environment variable {env_var} not set"
                )
        
        model_class = ModelFactory.PROVIDERS[provider]
        return model_class(
            model_name=model_name,
            model_id=model_id,
            api_key=api_key,
            **config
        )

    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> BaseModel:
        """Create model from configuration dictionary.
        
        Args:
            config: Configuration dict with:
                - provider: Provider name
                - model_name: Model name
                - model_id: Model ID
                - api_key: Optional API key
                - temperature: Optional temperature
                - max_tokens: Optional max tokens
                
        Returns:
            Initialized model instance
        """
        required_keys = ["provider", "model_name", "model_id"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")
        
        return ModelFactory.create_model(
            provider=config["provider"],
            model_name=config["model_name"],
            model_id=config["model_id"],
            api_key=config.get("api_key"),
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 2048),
        )

    @staticmethod
    def create_multiple(configs: list) -> Dict[str, BaseModel]:
        """Create multiple model instances.
        
        Args:
            configs: List of configuration dicts
            
        Returns:
            Dictionary mapping model names to instances
        """
        models = {}
        for config in configs:
            model = ModelFactory.create_from_config(config)
            models[model.model_name] = model
        return models
