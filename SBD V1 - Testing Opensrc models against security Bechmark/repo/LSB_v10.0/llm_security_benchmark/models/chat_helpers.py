"""Multi-turn chat helpers for LSB_v6 true conversational injection eval."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from models.base_model import BaseModel, ModelResponse


def chat(
    model: BaseModel,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.0,
) -> Tuple[str, int, float]:
    """Send a multi-turn message list; return (assistant_text, tokens, latency_sec)."""
    provider = type(model).__name__.lower()
    started = time.time()
    if "groq" in provider:
        text, tokens = _groq_chat(model, messages, max_tokens, temperature)
    elif "gemini" in provider:
        text, tokens = _gemini_chat(model, messages, max_tokens, temperature)
    elif "cohere" in provider:
        text, tokens = _cohere_chat(model, messages, max_tokens, temperature)
    elif "mistral" in provider:
        text, tokens = model._chat(messages, max_tokens=max_tokens, temperature=temperature)
    else:
        # Fallback: concatenate history into one user prompt.
        blob = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        resp = model.generate(blob, num_samples=1, max_tokens=max_tokens, temperature=temperature)[0]
        text, tokens = resp.response or "", resp.tokens_used or 0
    return text, tokens, time.time() - started


def _groq_chat(model: Any, messages: List[Dict[str, str]], max_tokens: int, temperature: float):
    request = {
        "messages": messages,
        "model": model.model_id,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "tool_choice": "none",
    }
    mid = model.model_id.lower()
    if "gpt-oss" in mid:
        request["reasoning_effort"] = "low"
    elif "qwen" in mid:
        request["reasoning_effort"] = "none"
    try:
        completion = model.client.chat.completions.create(**request)
    except Exception as err:
        msg = str(err).lower()
        if "reasoning_effort" in msg:
            request.pop("reasoning_effort", None)
            completion = model.client.chat.completions.create(**request)
        elif "tool choice" in msg:
            request.pop("tool_choice", None)
            completion = model.client.chat.completions.create(**request)
        else:
            raise
    choice = completion.choices[0]
    text = model._extract_text(choice)
    usage = completion.usage
    tokens = getattr(usage, "total_tokens", None) or getattr(usage, "completion_tokens", 0) or 0
    return text, tokens


def _gemini_chat(model: Any, messages: List[Dict[str, str]], max_tokens: int, temperature: float):
    # Flatten to alternating user/model contents for google-genai.
    from google.genai import types

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        if msg["role"] == "system":
            # Prepend system as user instruction.
            contents.append(types.Content(role="user", parts=[types.Part(text=f"[SYSTEM]\n{msg['content']}")]))
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    if model._use_v2:
        # Avoid thinking_config first — flash-lite/gemma 400s still consume free-tier RPM.
        try:
            response = model._client_v2.models.generate_content(
                model=model.model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception:
            response = model._client_v2.models.generate_content(
                model=model.model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        return model._extract_text(response), model._extract_tokens(response)
    # Legacy: concatenate.
    blob = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    return model._generate_legacy(blob, max_tokens, temperature)


def _cohere_chat(model: Any, messages: List[Dict[str, str]], max_tokens: int, temperature: float):
    if model._client_v2 is not None:
        result = model._client_v2.chat(
            model=model.model_id,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = ""
        message = getattr(result, "message", None)
        if message is not None:
            content = getattr(message, "content", None) or []
            parts = []
            for part in content:
                if getattr(part, "text", None):
                    parts.append(part.text)
            text = "\n".join(parts).strip()
        tokens = 0
        usage = getattr(result, "usage", None)
        if usage is not None:
            billed = getattr(usage, "billed_units", None) or getattr(usage, "tokens", None)
            if billed is not None:
                tokens = (getattr(billed, "input_tokens", 0) or 0) + (getattr(billed, "output_tokens", 0) or 0)
        return text, tokens
    # v1: use chat_history
    history = []
    user_msg = ""
    for msg in messages:
        if msg["role"] == "user":
            user_msg = msg["content"]
        elif msg["role"] == "assistant":
            history.append({"role": "CHATBOT", "message": msg["content"]})
            if user_msg:
                history.insert(-1, {"role": "USER", "message": user_msg})
                user_msg = ""
    result = model._client_v1.chat(
        model=model.model_id,
        message=user_msg or messages[-1]["content"],
        chat_history=history,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = (getattr(result, "text", None) or "").strip()
    return text, 0
