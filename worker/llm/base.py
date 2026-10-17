"""One small interface over several LLM providers.

The worker asks the model for JSON (plans, actions, extractions). Providers
differ in how they return it, so this layer normalises: a `complete()` call
returns text, parsed JSON when asked, and token usage with an estimated cost.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field


@dataclass
class LLMResult:
    text: str
    json: dict | list | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    latency_ms: int = 0
    raw: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    pass


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply, tolerating fences and prose."""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # find the outermost balanced object or array
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
    return None


# USD per million tokens (input, output). Used only for the cost column in reports.
PRICES = {
    "gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-flash-lite": (0.10, 0.40), "gemini-2.0-flash": (0.10, 0.40),
    "gemini-3-flash": (0.30, 2.50), "gemini-3.5-flash": (0.30, 2.50),
    "llama-3.3-70b-versatile": (0.59, 0.79), "openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.10, 0.50),
    "claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0),
}


def estimate_cost(model: str, inp: int, out: int) -> float:
    for key, (pi, po) in PRICES.items():
        if key in model:
            return (inp * pi + out * po) / 1e6
    return 0.0


class LLM:
    """Provider-agnostic chat completion. Subclasses implement `_call`."""

    name = "base"
    model = ""
    supports_vision = False

    def __init__(self, model: str, temperature: float = 0.0, max_tokens: int = 2048, timeout: float = 120.0):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def complete(self, system: str, messages: list[dict], want_json: bool = True, images: list[bytes] | None = None,
                 retries: int = 3) -> LLMResult:
        last_err = None
        for attempt in range(retries):
            t0 = time.time()
            try:
                text, inp, out, raw = self._call(system, messages, want_json, images or [])
            except LLMError as e:
                last_err = e
                time.sleep(min(2 ** attempt, 8))
                continue
            latency = int((time.time() - t0) * 1000)
            parsed = extract_json(text) if want_json else None
            if want_json and parsed is None and attempt < retries - 1:
                # ask once more, more firmly
                messages = messages + [{"role": "assistant", "content": text},
                                       {"role": "user", "content": "Reply with valid JSON only, no prose."}]
                last_err = LLMError("model did not return JSON")
                continue
            cost = estimate_cost(self.model, inp, out)
            self.calls += 1
            self.input_tokens += inp
            self.output_tokens += out
            self.cost_usd += cost
            return LLMResult(text=text, json=parsed, input_tokens=inp, output_tokens=out, cost_usd=cost,
                             model=self.model, latency_ms=latency, raw=raw)
        raise LLMError(f"LLM call failed after {retries} attempts: {last_err}")

    def _call(self, system: str, messages: list[dict], want_json: bool, images: list[bytes]):
        raise NotImplementedError
