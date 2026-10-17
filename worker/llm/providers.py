"""Concrete LLM providers. All use plain HTTPS so there are no heavy SDKs.

- Gemini (free tier works): GEMINI_API_KEY
- OpenAI-compatible (Groq, OpenRouter, Ollama, OpenAI): OPENAI_COMPAT_BASE_URL + OPENAI_COMPAT_API_KEY
- Anthropic: ANTHROPIC_API_KEY
"""
from __future__ import annotations

import base64
import os

import httpx

from worker.llm.base import LLM, LLMError


def _msgs_to_text(messages):
    return "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)


class GeminiLLM(LLM):
    name = "gemini"
    supports_vision = True

    def __init__(self, model="gemini-2.5-flash", api_key=None, **kw):
        super().__init__(model, **kw)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

    def _call(self, system, messages, want_json, images):
        contents = []
        for i, m in enumerate(messages):
            role = "model" if m["role"] == "assistant" else "user"
            parts = [{"text": m["content"]}]
            if images and i == len(messages) - 1 and role == "user":
                for img in images:
                    parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img).decode()}})
            contents.append({"role": role, "parts": parts})
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens,
                                 **({"responseMimeType": "application/json"} if want_json else {})},
        }
        url = f"{self.base}/models/{self.model}:generateContent"
        try:
            r = httpx.post(url, params={"key": self.api_key}, json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise LLMError(f"gemini request failed: {e}") from None
        if r.status_code in (429, 500, 502, 503):
            raise LLMError(f"gemini {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise LLMError(f"gemini: empty response {str(data)[:200]}")
        usage = data.get("usageMetadata", {})
        return text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), {"finish": data["candidates"][0].get("finishReason")}


class OpenAICompatLLM(LLM):
    """Groq, OpenRouter, Ollama, OpenAI: anything speaking /v1/chat/completions."""
    name = "openai_compat"
    supports_vision = False

    def __init__(self, model="openai/gpt-oss-120b", base_url=None, api_key=None, **kw):
        super().__init__(model, **kw)
        self.base_url = (base_url or os.environ.get("OPENAI_COMPAT_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_COMPAT_API_KEY") or os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY") or "none"

    def _call(self, system, messages, want_json, images):
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, *messages]}
        if want_json:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as e:
            raise LLMError(f"request failed: {e}") from None
        if r.status_code in (429, 500, 502, 503):
            raise LLMError(f"{self.base_url} {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            raise LLMError(f"{self.base_url} {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), {"finish": data["choices"][0].get("finish_reason")}


class AnthropicLLM(LLM):
    name = "anthropic"
    supports_vision = True

    def __init__(self, model="claude-haiku-5-5", api_key=None, **kw):
        super().__init__(model, **kw)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self.base = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com")

    def _call(self, system, messages, want_json, images):
        msgs = []
        for i, m in enumerate(messages):
            content = [{"type": "text", "text": m["content"]}]
            if images and i == len(messages) - 1 and m["role"] == "user":
                for img in images:
                    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                                "data": base64.b64encode(img).decode()}})
            msgs.append({"role": m["role"], "content": content})
        sys_text = system + ("\n\nReply with a single JSON value and nothing else." if want_json else "")
        body = {"model": self.model, "max_tokens": self.max_tokens, "system": sys_text, "messages": msgs}
        try:
            r = httpx.post(f"{self.base}/v1/messages", json=body, timeout=self.timeout,
                           headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        except httpx.HTTPError as e:
            raise LLMError(f"anthropic request failed: {e}") from None
        if r.status_code in (429, 500, 502, 503, 529):
            raise LLMError(f"anthropic {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            raise LLMError(f"anthropic {r.status_code}: {r.text[:300]}")
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0), {"stop": data.get("stop_reason")}


def make_llm(spec: str | None = None, **kw) -> LLM:
    """Build an LLM from a spec like 'gemini:gemini-2.5-flash', 'groq:openai/gpt-oss-120b',
    'openai_compat:<model>', 'anthropic:claude-haiku-5-5'. Defaults from LLM env var."""
    spec = spec or os.environ.get("LLM") or "gemini:gemini-2.5-flash"
    provider, _, model = spec.partition(":")
    provider = provider.lower()
    if provider == "gemini":
        return GeminiLLM(model or "gemini-2.5-flash", **kw)
    if provider in ("groq", "openai_compat", "openai", "openrouter", "ollama"):
        base = {"groq": "https://api.groq.com/openai/v1", "openai": "https://api.openai.com/v1",
                "openrouter": "https://openrouter.ai/api/v1", "ollama": "http://localhost:11434/v1"}.get(provider)
        return OpenAICompatLLM(model or "openai/gpt-oss-120b", base_url=os.environ.get("OPENAI_COMPAT_BASE_URL") or base, **kw)
    if provider == "anthropic":
        return AnthropicLLM(model or "claude-haiku-5-5", **kw)
    raise LLMError(f"unknown LLM provider '{provider}' (use gemini:, groq:, openai_compat:, anthropic:)")
