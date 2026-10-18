"""Concrete LLM providers. All use plain HTTPS so there are no heavy SDKs.

- Gemini (free tier works): GEMINI_API_KEY
- OpenAI-compatible (Groq, OpenRouter, Ollama, OpenAI): OPENAI_COMPAT_BASE_URL + OPENAI_COMPAT_API_KEY
- Anthropic: ANTHROPIC_API_KEY
"""
from __future__ import annotations

import base64
import os
import time

import httpx

from worker.llm.base import LLM, LLMError


def _msgs_to_text(messages):
    return "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)


class GeminiLLM(LLM):
    name = "gemini"
    supports_vision = True

    PREFERRED = ("gemini-3-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.0-flash")

    def __init__(self, model="auto", api_key=None, **kw):
        super().__init__(model, **kw)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        if model in ("", "auto"):
            self.model = self.pick_model()

    def pick_model(self) -> str:
        """Free-tier model availability changes; ask the API which Flash models this key can use."""
        try:
            r = httpx.get(f"{self.base}/models", params={"key": self.api_key, "pageSize": 200}, timeout=30)
            names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        except (httpx.HTTPError, ValueError, KeyError):
            return "gemini-2.5-flash"
        for pref in self.PREFERRED:
            for n in names:
                if n == pref or n.startswith(pref + "-"):
                    return n
        flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n and "live" not in n]
        return flash[0] if flash else "gemini-2.5-flash"

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


def _seconds(text: str) -> float:
    """Parse '20.745s', '1m26.4s', '585ms', '7' into seconds."""
    text = (text or "").strip()
    if not text:
        return 0.0
    if text.replace(".", "", 1).isdigit():
        return float(text)
    total, num = 0.0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isdigit() or ch == ".":
            num += ch
            i += 1
            continue
        unit = ch
        if text[i:i + 2] == "ms":
            unit, i = "ms", i + 2
        else:
            i += 1
        value = float(num or 0)
        total += value * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}.get(unit, 0)
        num = ""
    return total


class OpenAICompatLLM(LLM):
    """Groq, OpenRouter, Ollama, OpenAI: anything speaking /v1/chat/completions.

    Free tiers meter tokens per minute. The client reads the rate-limit headers
    and waits for the reset instead of failing, so a run slows down rather than
    dying when the quota is tight.
    """
    name = "openai_compat"
    supports_vision = False

    def __init__(self, model="openai/gpt-oss-120b", base_url=None, api_key=None, **kw):
        super().__init__(model, **kw)
        self.base_url = (base_url or os.environ.get("OPENAI_COMPAT_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_COMPAT_API_KEY") or os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY") or "none"
        self.remaining_tokens = None
        self.tokens_reset_at = 0.0
        self.waited_s = 0.0

    def _pace(self, estimated_tokens: int):
        """If the minute's token budget is nearly used, sleep until it resets."""
        if self.remaining_tokens is not None and self.remaining_tokens < estimated_tokens:
            wait = max(0.0, self.tokens_reset_at - time.time()) + 0.5
            if wait > 0:
                time.sleep(min(wait, 90))
                self.waited_s += min(wait, 90)
                self.remaining_tokens = None

    def _note_headers(self, headers):
        try:
            if "x-ratelimit-remaining-tokens" in headers:
                self.remaining_tokens = int(float(headers["x-ratelimit-remaining-tokens"]))
            if "x-ratelimit-reset-tokens" in headers:
                self.tokens_reset_at = time.time() + _seconds(headers["x-ratelimit-reset-tokens"])
        except ValueError:
            pass

    def _call(self, system, messages, want_json, images):
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, *messages]}
        if want_json:
            body["response_format"] = {"type": "json_object"}
        estimated = (len(system) + sum(len(m["content"]) for m in messages)) // 3 + self.max_tokens // 4
        for attempt in range(8):
            self._pace(estimated)
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout,
                               headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.HTTPError as e:
                raise LLMError(f"request failed: {e}") from None
            self._note_headers(r.headers)
            if r.status_code == 429:
                wait = _seconds(r.headers.get("retry-after", "")) or max(1.0, self.tokens_reset_at - time.time()) or 5.0
                wait = min(max(wait, 1.0), 90.0)
                time.sleep(wait)
                self.waited_s += wait
                self.remaining_tokens = None
                continue
            if r.status_code in (500, 502, 503):
                time.sleep(min(2 ** attempt, 20))
                continue
            break
        if r.status_code == 429:
            raise LLMError(f"{self.base_url} 429 after waiting: {r.text[:200]}")
        if r.status_code in (500, 502, 503):
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
    spec = spec or os.environ.get("LLM") or "gemini:auto"
    provider, _, model = spec.partition(":")
    provider = provider.lower()
    if provider == "gemini":
        return GeminiLLM(model or "auto", **kw)
    if provider in ("groq", "openai_compat", "openai", "openrouter", "ollama"):
        base = {"groq": "https://api.groq.com/openai/v1", "openai": "https://api.openai.com/v1",
                "openrouter": "https://openrouter.ai/api/v1", "ollama": "http://localhost:11434/v1"}.get(provider)
        return OpenAICompatLLM(model or "openai/gpt-oss-120b", base_url=os.environ.get("OPENAI_COMPAT_BASE_URL") or base, **kw)
    if provider == "anthropic":
        return AnthropicLLM(model or "claude-haiku-5-5", **kw)
    raise LLMError(f"unknown LLM provider '{provider}' (use gemini:, groq:, openai_compat:, anthropic:)")
