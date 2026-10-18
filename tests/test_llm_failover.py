"""Budget failover: a model whose daily quota is gone is parked and the next one takes over; nothing sleeps for hours."""
import time

import pytest

from worker.llm.base import LLM, BudgetExhausted, LLMError
from worker.llm.providers import FailoverLLM, GeminiLLM, OpenAICompatLLM, make_llm


class Fake(LLM):
    def __init__(self, model, fail=False):
        super().__init__(model)
        self.fail = fail

    def _call(self, system, messages, want_json, images):
        if self.fail:
            raise BudgetExhausted(f"{self.model} out of tokens", retry_after=2739, model=self.model)
        return '{"ok": true}', 10, 2, {}


def no_sleep(seconds):
    raise AssertionError(f"slept {seconds}s")


def test_failover_switches_and_reports_both_models(monkeypatch):
    monkeypatch.setattr(time, "sleep", no_sleep)
    llm = FailoverLLM([Fake("a", fail=True), Fake("b")])
    res = llm.complete("s", [{"role": "user", "content": "u"}])
    assert res.json == {"ok": True}
    assert llm.model == "a -> b" and llm.calls == 1 and llm.input_tokens == 10


def test_all_exhausted_fails_fast(monkeypatch):
    monkeypatch.setattr(time, "sleep", no_sleep)
    llm = FailoverLLM([Fake("a", fail=True), Fake("b", fail=True)])     # resets in 45 min: beyond the wait budget
    with pytest.raises(LLMError, match="every model is unavailable"):
        llm.complete("s", [{"role": "user", "content": "u"}])


class Flaky(Fake):
    def __init__(self, model, failures):
        super().__init__(model)
        self.failures = failures

    def _call(self, system, messages, want_json, images):
        if self.failures:
            self.failures -= 1
            raise LLMError(f"{self.model} 503: overloaded")
        return '{"ok": true}', 10, 2, {}


def test_overloaded_model_rests_and_the_next_one_answers(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    llm = FailoverLLM([Flaky("a", failures=99), Fake("b")])
    assert llm.complete("s", [{"role": "user", "content": "u"}]).json == {"ok": True}
    assert llm.model == "a -> b" and 0 in llm.parked


def test_waits_for_a_short_reset_instead_of_giving_up(monkeypatch):
    slept, clock = [], [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)))
    llm = FailoverLLM([Flaky("a", failures=3)], max_wait_s=600)     # 3 failures = one rested attempt
    assert llm.complete("s", [{"role": "user", "content": "u"}]).json == {"ok": True}
    assert any(170 < s <= 182 for s in slept)                        # waited out the 180 s rest


def test_budget_exhausted_is_not_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", no_sleep)
    with pytest.raises(BudgetExhausted):
        Fake("a", fail=True).complete("s", [{"role": "user", "content": "u"}])


class Resp:
    def __init__(self, status, text, headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def json(self):
        return {}


def test_groq_daily_limit_raises_budget_exhausted(monkeypatch):
    import worker.llm.providers as P
    monkeypatch.setattr(time, "sleep", no_sleep)
    body = ("Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000, Used 199265, "
            "Requested 7073. Please try again in 45m38s.")
    monkeypatch.setattr(P.httpx, "post", lambda *a, **k: Resp(429, body, {"retry-after": "2739"}))
    llm = OpenAICompatLLM("openai/gpt-oss-120b", api_key="x")
    with pytest.raises(BudgetExhausted) as e:
        llm._call("s", [{"role": "user", "content": "u"}], True, [])
    assert e.value.retry_after == 2739


def test_gemini_daily_limit_raises_budget_exhausted(monkeypatch):
    import worker.llm.providers as P
    monkeypatch.setattr(time, "sleep", no_sleep)
    body = '{"error": {"message": "Quota exceeded for metric GenerateRequestsPerDayPerProjectPerModel", "details": [{"retryDelay": "3h"}]}}'
    monkeypatch.setattr(P.httpx, "post", lambda *a, **k: Resp(429, body))
    llm = GeminiLLM("gemini-3.8-flash", api_key="x")
    with pytest.raises(BudgetExhausted):
        llm._call("s", [{"role": "user", "content": "u"}], True, [])


def test_make_llm_builds_failover_from_a_list(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    llm = make_llm("groq:openai/gpt-oss-120b,gemini:gemini-3.8-flash")
    assert isinstance(llm, FailoverLLM) and llm.model == "openai/gpt-oss-120b"
    assert llm.supports_vision is False     # follows the model currently in use


def test_gemini_key_goes_in_a_header_never_the_url(monkeypatch):
    import worker.llm.providers as P
    seen = {}

    def fake_post(url, **kw):
        seen.update(url=url, params=kw.get("params"), headers=kw.get("headers"))
        return Resp(200, "{}")

    class R(Resp):
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}], "usageMetadata": {}}

    monkeypatch.setattr(P.httpx, "post", lambda url, **kw: (seen.update(url=url, params=kw.get("params"), headers=kw.get("headers")), R(200, ""))[1])
    GeminiLLM("gemini-3.8-flash", api_key="SECRET")._call("s", [{"role": "user", "content": "u"}], True, [])
    assert "SECRET" not in seen["url"] and not seen["params"] and seen["headers"]["x-goog-api-key"] == "SECRET"


def test_gemini_learns_its_rpm_quota_and_paces(monkeypatch):
    import worker.llm.providers as P
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    body = ('{"error":{"details":[{"violations":[{"quotaMetric":"generativelanguage.googleapis.com/generate_content_free_tier_requests",'
            '"quotaId":"GenerateRequestsPerMinutePerProjectPerModel-FreeTier","quotaDimensions":{"model":"gemini-3.8-flash","location":"global"},'
            '"quotaValue":"5"}]},{"retryDelay":"21s"}]}}')
    monkeypatch.setattr(P.httpx, "post", lambda url, **kw: Resp(429, body))
    llm = GeminiLLM("gemini-3.8-flash", api_key="x")
    with pytest.raises(LLMError, match="PerMinute"):
        llm._call("s", [{"role": "user", "content": "u"}], True, [])
    assert llm.rpm_limit == 5 and slept == [21.0]
    llm._sent = [time.time() - 1] * 5           # five requests in the last minute: the sixth must wait
    llm._pace()
    assert len(slept) == 2 and 58 < slept[-1] <= 60.5
