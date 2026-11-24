"""Model factory for creating LLM connectors."""

import os
from typing import Dict, Any, Optional, Type
from .base_model import BaseModel


class ModelFactory:
    """Factory for creating model connectors."""

    PROVIDER_MODULES = {
        "openai": (".openai_model", "OpenAIModel"),
        "google": (".gemini_model", "GeminiModel"),
        "gemini": (".gemini_model", "GeminiModel"),
        "mistral": (".mistral_model", "MistralModel"),
        "anthropic": (".anthropic_model", "AnthropicModel"),
        "groq": (".groq_model", "GroqModel"),
        "xai": (".xai_model", "XAIModel"),
        "grok": (".xai_model", "XAIModel"),
        "cohere": (".cohere_model", "CohereModel"),
    }

    @staticmethod
    def _load_provider(provider: str) -> Type[BaseModel]:
        from importlib import import_module

        if provider not in ModelFactory.PROVIDER_MODULES:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported: {list(ModelFactory.PROVIDER_MODULES.keys())}"
            )
        module_name, class_name = ModelFactory.PROVIDER_MODULES[provider]
        module = import_module(module_name, package="models")
        return getattr(module, class_name)

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
        model_class = ModelFactory._load_provider(provider)
        
        # Get API key from parameter or environment
        if api_key is None:
            env_var_map = {
                "openai": ["OPENAI_API_KEY"],
                "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
                "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
                "mistral": ["MISTRAL_API_KEY"],
                "anthropic": ["ANTHROPIC_API_KEY"],
                "groq": ["GROQ_API_KEY"],
                "xai": ["XAI_API_KEY"],
                "grok": ["XAI_API_KEY"],
                "cohere": ["COHERE_API_KEY"],
            }
            env_vars = env_var_map.get(provider, [])
            for env_var in env_vars:
                api_key = os.getenv(env_var)
                if api_key:
                    break

            if not api_key:
                raise RuntimeError(
                    f"API key for {provider} not provided and "
                    f"environment variable(s) {env_vars} not set"
                )
        
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
