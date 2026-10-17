"""A fake LLM for tests: replies from a queue or from a function of the prompt.

Lets the LLM brain's prompt plumbing be tested without a network or a key:
JSON parsing, milestone bookkeeping, unknown-tool handling, vision attachment.
"""
from __future__ import annotations

import json

from worker.llm.base import LLM, LLMError


class FakeLLM(LLM):
    name = "fake"
    supports_vision = True

    def __init__(self, replies=None, responder=None):
        super().__init__("fake-model")
        self.replies = list(replies or [])
        self.responder = responder
        self.prompts: list[tuple[str, list[dict], list]] = []

    def _call(self, system, messages, want_json, images):
        self.prompts.append((system, messages, images))
        if self.responder:
            reply = self.responder(system, messages)
        elif self.replies:
            reply = self.replies.pop(0)
        else:
            raise LLMError("fake LLM has no reply queued")
        if not isinstance(reply, str):
            reply = json.dumps(reply)
        return reply, len(system) // 4 + sum(len(m["content"]) for m in messages) // 4, len(reply) // 4, {}
