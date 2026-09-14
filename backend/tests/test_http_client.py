import httpx
import pytest

from app.providers.http import (
    ProviderError,
    RequestBudget,
    RequestBudgetExceededError,
    ResilientHttpClient,
    RetryableResponseError,
    RetryPolicy,
)


class Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def make(recorder, attempts=4):
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    http = ResilientHttpClient(client, retry=RetryPolicy(max_attempts=attempts), sleep=fake_sleep)
    return http, sleeps, client


async def test_retries_429_honouring_retry_after_then_succeeds():
    rec = Recorder(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": 1})]
    )
    http, sleeps, client = await make(rec)
    async with client:
        assert await http.request_json("GET", "https://api.test/x") == {"ok": 1}
    assert sleeps == [7.0]
    assert len(rec.urls) == 2


async def test_non_retryable_status_fails_immediately():
    rec = Recorder([httpx.Response(403, text="key invalid")])
    http, sleeps, client = await make(rec)
    async with client:
        with pytest.raises(ProviderError) as exc:
            await http.request_json("GET", "https://api.test/x")
    assert exc.value.status_code == 403
    assert sleeps == []


async def test_html_body_with_200_is_retried():
    rec = Recorder([httpx.Response(200, text="<html>busy</html>"), httpx.Response(200, json=[])])
    http, _, client = await make(rec)
    async with client:
        assert await http.request_json("GET", "https://api.test/x") == []


async def test_validator_can_request_a_retry():
    rec = Recorder(
        [httpx.Response(200, json={"remark": "busy"}), httpx.Response(200, json={"remark": ""})]
    )

    def validate(body):
        if body["remark"]:
            raise RetryableResponseError("busy")

    http, _, client = await make(rec)
    async with client:
        assert await http.request_json("GET", "https://api.test/x", validate=validate) == {
            "remark": ""
        }


async def test_gives_up_after_max_attempts_and_rotates_urls():
    rec = Recorder([httpx.ConnectTimeout("t"), httpx.Response(503), httpx.ReadTimeout("t")])
    http, sleeps, client = await make(rec, attempts=3)
    mirrors = ["https://a.test/api", "https://b.test/api"]
    async with client:
        with pytest.raises(ProviderError, match="gave up after 3 attempts"):
            await http.request_json("POST", lambda n: mirrors[(n - 1) % 2])
    assert rec.urls == ["https://a.test/api", "https://b.test/api", "https://a.test/api"]
    assert len(sleeps) == 2


async def test_budget_counts_retries_and_stops_requests():
    rec = Recorder([httpx.Response(500), httpx.Response(500), httpx.Response(200, json={})])
    http, _, client = await make(rec)
    budget = RequestBudget(limit=2)
    async with client:
        with pytest.raises(RequestBudgetExceededError):
            await http.request_json("GET", "https://api.test/x", budget=budget)
    assert budget.used == 2
    assert len(rec.urls) == 2


def test_backoff_is_bounded_by_the_exponential_ceiling():
    policy = RetryPolicy(base_delay_s=1, max_delay_s=5)
    for attempt, ceiling in [(1, 1), (2, 2), (3, 4), (4, 5), (9, 5)]:
        assert 0 <= policy.backoff(attempt) <= ceiling
