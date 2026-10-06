"""Public applicant-tracking-system job board APIs (Greenhouse, Lever, Ashby)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from saathi.domain.models import Item
from saathi.domain.ports import Clock, HttpClient

BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
    "lever": "https://api.lever.co/v0/postings/{board}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{board}",
}


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _normalize(provider: str, row: dict[str, Any]) -> tuple[str, str, str, datetime | None]:
    """Return title, URL, location, and posted time for one provider row."""

    if provider == "greenhouse":
        location = row.get("location")
        place = str(location.get("name", "")) if isinstance(location, dict) else ""
        when = row.get("first_published") or row.get("updated_at")
        return str(row.get("title", "")), str(row.get("absolute_url", "")), place, _parse_time(when)
    if provider == "lever":
        categories = row.get("categories")
        place = str(categories.get("location", "")) if isinstance(categories, dict) else ""
        return (
            str(row.get("text", "")),
            str(row.get("hostedUrl", "")),
            place,
            _parse_time(row.get("createdAt")),
        )
    place = str(row.get("location", ""))
    if row.get("isRemote"):
        place = f"{place} (remote)".strip()
    return (
        str(row.get("title", "")),
        str(row.get("jobUrl", "")),
        place,
        _parse_time(row.get("publishedAt")),
    )


class JobBoardSource:
    """List a company's open roles whose titles match configured patterns."""

    def __init__(
        self,
        name: str,
        provider: str,
        board: str,
        http: HttpClient,
        clock: Clock,
        *,
        title_patterns: list[str],
        location_patterns: list[str] | None = None,
        max_age_days: int = 30,
        limit: int = 10,
    ) -> None:
        if provider not in BOARD_URLS:
            raise ValueError(f"unknown job board provider: {provider}")
        self.name = name
        self._url = BOARD_URLS[provider].format(board=quote(board, safe=""))
        self._provider = provider
        self._http = http
        self._clock = clock
        self._titles = [re.compile(pattern, re.IGNORECASE) for pattern in title_patterns]
        self._locations = [
            re.compile(pattern, re.IGNORECASE) for pattern in location_patterns or []
        ]
        self._max_age = timedelta(days=max_age_days)
        self._limit = limit

    def collect(self) -> list[Item]:
        """Fetch the board and keep recent postings matching title and location filters."""

        data = self._http.get_json(self._url)
        rows = data.get("jobs", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        cutoff = self._clock.now() - self._max_age
        items: list[Item] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("isListed") is False:
                continue
            title, url, place, posted = _normalize(self._provider, row)
            if not url or not any(pattern.search(title) for pattern in self._titles):
                continue
            if self._locations and not any(pattern.search(place) for pattern in self._locations):
                continue
            if posted is not None and posted < cutoff:
                continue
            items.append(
                Item(title=title, url=url, source=self.name, published_at=posted, summary=place)
            )
        items.sort(key=lambda item: item.published_at or cutoff, reverse=True)
        return items[: self._limit]
