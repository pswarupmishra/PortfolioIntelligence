import json

import httpx
import pytest

from app.jira import JiraClient, JiraError


@pytest.mark.asyncio
async def test_project_pagination_fetches_every_page() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startAt"])
        calls.append(start)
        values = [{"id": "1", "key": "ONE", "name": "One"}] if start == 0 else [{"id": "2", "key": "TWO", "name": "Two"}]
        return httpx.Response(200, json={"values": values, "startAt": start, "maxResults": 1, "total": 2, "isLast": start == 1})

    async with JiraClient("https://example.atlassian.net", "a@b.com", "secret", transport=httpx.MockTransport(handler)) as client:
        client_page_size = client.paged
        items = [x async for x in client_page_size("/rest/api/3/project/search", value_key="values", page_size=1)]
    assert [x["id"] for x in items] == ["1", "2"]
    assert calls == [0, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [(401, "jira_unauthorized"), (403, "jira_forbidden")])
async def test_auth_errors_are_typed(status: int, code: str) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"errorMessages": ["no"]}))
    async with JiraClient("https://example.atlassian.net", "a", "b", transport=transport) as client:
        with pytest.raises(JiraError) as caught:
            await client.myself()
    assert caught.value.code == code
    assert "secret" not in json.dumps(caught.value.details)


@pytest.mark.asyncio
async def test_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    async def no_sleep(_: float) -> None:
        pass

    monkeypatch.setattr("app.jira.asyncio.sleep", no_sleep)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "0"}) if attempts == 1 else httpx.Response(200, json={"accountId": "abc"})

    async with JiraClient("https://example.atlassian.net", "a", "b", transport=httpx.MockTransport(handler)) as client:
        result = await client.myself()
    assert result["accountId"] == "abc"
    assert attempts == 2


@pytest.mark.asyncio
async def test_exhausted_rate_limit_is_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        pass

    monkeypatch.setattr("app.jira.asyncio.sleep", no_sleep)
    transport = httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "0"}))
    async with JiraClient("https://example.atlassian.net", "a", "b", max_retries=1, transport=transport) as client:
        with pytest.raises(JiraError) as caught:
            await client.myself()
    assert caught.value.code == "jira_rate_limited"
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_enhanced_jql_uses_next_page_token() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "nextPageToken" not in body:
            return httpx.Response(200, json={"issues": [{"id": "1"}], "nextPageToken": "next"})
        return httpx.Response(200, json={"issues": [{"id": "2"}], "isLast": True})

    async with JiraClient("https://example.atlassian.net", "a", "b", transport=httpx.MockTransport(handler)) as client:
        issues = [item async for item in client.search_issues("project = 1", ["*all"])]
    assert [item["id"] for item in issues] == ["1", "2"]
    assert bodies[1]["nextPageToken"] == "next"
    assert all(body["fieldsByKeys"] is False for body in bodies)
