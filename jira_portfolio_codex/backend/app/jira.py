import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, cast
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


class JiraError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.status_code, self.details = code, message, status_code, details or {}


class JiraClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        *,
        max_retries: int = 3,
        timeout: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=base_url, auth=(email, api_token), timeout=timeout, transport=transport, headers={"Accept": "application/json"}
        )

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        correlation_id = str(uuid4())
        headers = {**kwargs.pop("headers", {}), "X-Correlation-ID": correlation_id}
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.request(method, path, headers=headers, **kwargs)
            except httpx.RequestError as exc:
                if attempt == self.max_retries:
                    raise JiraError("jira_unavailable", "Could not reach Jira", details={"reason": str(exc)}) from exc
                await asyncio.sleep(min(2**attempt, 8))
                continue
            if response.status_code == 429 and attempt < self.max_retries:
                await asyncio.sleep(self._retry_delay(response.headers.get("Retry-After"), attempt))
                continue
            if response.status_code in (401, 403):
                code = "jira_unauthorized" if response.status_code == 401 else "jira_forbidden"
                message = "Jira credentials were rejected" if response.status_code == 401 else "Jira denied access to this resource"
                raise JiraError(code, message, response.status_code)
            if response.status_code == 429:
                raise JiraError("jira_rate_limited", "Jira rate limit retry budget exhausted", 503)
            if response.is_error:
                raise JiraError("jira_api_error", f"Jira returned HTTP {response.status_code}", 502, {"jira_status": response.status_code})
            if not response.content:
                return None
            return response.json()
        raise AssertionError("unreachable")

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        if value:
            try:
                return min(float(value), 60)
            except ValueError:
                try:
                    target = parsedate_to_datetime(value)
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=timezone.utc)
                    return float(max(0, min((target - datetime.now(timezone.utc)).total_seconds(), 60)))
                except (TypeError, ValueError):
                    pass
        return float(min(2**attempt, 8))

    async def myself(self) -> dict[str, Any]:
        return cast(dict[str, Any], await self.request("GET", "/rest/api/3/myself"))

    async def paged(
        self, path: str, *, value_key: str, params: dict[str, Any] | None = None, page_size: int = 50
    ) -> AsyncIterator[dict[str, Any]]:
        start_at = 0
        while True:
            data = await self.request("GET", path, params={**(params or {}), "startAt": start_at, "maxResults": page_size})
            values = data.get(value_key, [])
            for value in values:
                yield value
            if data.get("isLast") is True or not values or start_at + len(values) >= data.get("total", start_at + len(values)):
                break
            start_at += len(values)

    async def projects(self) -> list[dict[str, Any]]:
        return [item async for item in self.paged("/rest/api/3/project/search", value_key="values")]

    async def fields(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/rest/api/3/field")
        return data if isinstance(data, list) else data.get("values", [])

    async def issue_types(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/rest/api/3/issuetype")
        return data if isinstance(data, list) else data.get("values", [])

    async def statuses(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/rest/api/3/status")
        return data if isinstance(data, list) else data.get("values", [])

    async def field_contexts(self, field_id: str) -> list[dict[str, Any]]:
        return [item async for item in self.paged(f"/rest/api/3/field/{field_id}/context", value_key="values")]

    async def context_options(self, field_id: str, context_id: str) -> list[dict[str, Any]]:
        path = f"/rest/api/3/field/{field_id}/context/{context_id}/option"
        return [item async for item in self.paged(path, value_key="values")]

    async def search_issues(self, jql: str, fields: list[str], page_size: int = 100) -> AsyncIterator[dict[str, Any]]:
        next_page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "fields": fields,
                "fieldsByKeys": False,
                "maxResults": page_size,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            data = await self.request("POST", "/rest/api/3/search/jql", json=body)
            for issue in data.get("issues", []):
                yield issue
            next_page_token = data.get("nextPageToken")
            if data.get("isLast") is True or not next_page_token:
                break
