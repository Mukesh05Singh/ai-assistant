"""Config-driven source adapter registry."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from saathi.adapters.appstore import AppStoreReviewsSource
from saathi.adapters.arxiv import arxiv_source
from saathi.adapters.federal_register import FederalRegisterSource
from saathi.adapters.github import GitHubTrendingSource
from saathi.adapters.google_news import google_news_source
from saathi.adapters.hackernews import HackerNewsSource
from saathi.adapters.hermes_outputs import HermesOutputsSource
from saathi.adapters.job_boards import JobBoardSource
from saathi.adapters.openfda import OpenFdaRecallSource
from saathi.adapters.question_bank import QuestionBankSource
from saathi.adapters.reddit import reddit_source
from saathi.adapters.rss import RssSource
from saathi.adapters.youtube import youtube_source
from saathi.domain.config import ConfigError, required_string
from saathi.domain.ports import Clock, HttpClient, Source, StateStore

SourceBuilder = Callable[[str, dict[str, Any], HttpClient, StateStore, Clock], Source]
SOURCE_TYPES: dict[str, SourceBuilder] = {}


def source_type(name: str) -> Callable[[SourceBuilder], SourceBuilder]:
    """Register a configurable source adapter type."""

    def decorate(builder: SourceBuilder) -> SourceBuilder:
        SOURCE_TYPES[name] = builder
        return builder

    return decorate


def _strings(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{context} must be a list of strings")
    return value


@source_type("rss")
def _rss(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, clock: Clock) -> Source:
    return RssSource(name, required_string(row, "url", name), http, clock)


@source_type("reddit")
def _reddit(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock) -> Source:
    query = row.get("query")
    if query is not None and not isinstance(query, str):
        raise ConfigError(f"{name}.query must be a string")
    return reddit_source(required_string(row, "subreddit", name), http, __, query=query)


@source_type("google_news")
def _gnews(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock) -> Source:
    return google_news_source(name, required_string(row, "query", name), http, __)


@source_type("hackernews")
def _hackernews(
    name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock
) -> Source:
    return HackerNewsSource(http, _strings(row.get("keywords"), f"{name}.keywords"))


@source_type("github")
def _github(
    name: str, row: dict[str, Any], http: HttpClient, state: StateStore, clock: Clock
) -> Source:
    return GitHubTrendingSource(
        http,
        state,
        clock,
        _strings(row.get("topics"), f"{name}.topics"),
        rate_delay=float(row.get("rate_delay_seconds", 6.1)),
    )


@source_type("arxiv")
def _arxiv(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock) -> Source:
    return arxiv_source(name, required_string(row, "query", name), http, __)


@source_type("youtube")
def _youtube(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock) -> Source:
    return youtube_source(name, required_string(row, "channel_id", name), http, __)


@source_type("appstore")
def _appstore(name: str, row: dict[str, Any], http: HttpClient, _: StateStore, __: Clock) -> Source:
    return AppStoreReviewsSource(name, required_string(row, "app_id", name), http)


@source_type("openfda")
def _openfda(
    name: str, row: dict[str, Any], http: HttpClient, _: StateStore, clock: Clock
) -> Source:
    return OpenFdaRecallSource(http, clock, int(row.get("lookback_days", 30)))


@source_type("federal_register")
def _federal(
    name: str, row: dict[str, Any], http: HttpClient, _: StateStore, clock: Clock
) -> Source:
    return FederalRegisterSource(required_string(row, "term", name), http, clock)


@source_type("hermes_outputs")
def _hermes_outputs(
    name: str, row: dict[str, Any], _: HttpClient, __: StateStore, ___: Clock
) -> Source:
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    names = _strings(row.get("job_names"), f"{name}.job_names")
    return HermesOutputsSource(
        name,
        home,
        names,
        max_age_hours=int(row.get("max_age_hours", 24)),
        characters=int(row.get("characters", 2500)),
    )


@source_type("job_board")
def _job_board(
    name: str, row: dict[str, Any], http: HttpClient, _: StateStore, clock: Clock
) -> Source:
    locations = row.get("location_patterns", [])
    try:
        return JobBoardSource(
            name,
            required_string(row, "provider", name),
            required_string(row, "board", name),
            http,
            clock,
            title_patterns=_strings(row.get("title_patterns"), f"{name}.title_patterns"),
            location_patterns=_strings(locations, f"{name}.location_patterns"),
            max_age_days=int(row.get("max_age_days", 30)),
            limit=int(row.get("limit", 10)),
        )
    except (ValueError, re.error) as exc:
        raise ConfigError(f"{name}: {exc}") from exc


@source_type("question_bank")
def _question_bank(
    name: str, row: dict[str, Any], _: HttpClient, __: StateStore, clock: Clock
) -> Source:
    path = Path(required_string(row, "path", name)).expanduser()
    return QuestionBankSource(
        name,
        path,
        clock,
        companies=_strings(row.get("companies"), f"{name}.companies"),
        per_company=int(row.get("per_company", 1)),
    )


def build_source(row: dict[str, Any], http: HttpClient, state: StateStore, clock: Clock) -> Source:
    """Instantiate a configured source through the adapter registry."""

    name = required_string(row, "name", "source")
    kind = required_string(row, "type", name)
    try:
        builder = SOURCE_TYPES[kind]
    except KeyError as exc:
        raise ConfigError(f"{name}.type is unknown: {kind}") from exc
    return builder(name, row, http, state, clock)
