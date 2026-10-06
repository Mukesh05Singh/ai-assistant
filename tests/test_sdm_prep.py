from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from saathi.adapters.job_boards import JobBoardSource
from saathi.adapters.question_bank import QuestionBankSource
from saathi.domain.config import ConfigError, load_yaml
from saathi.use_cases.setup import _customize_sources

ROOT = Path(__file__).resolve().parents[1]
EM = ["engineering manager", "software development manager"]


class FixedClock:
    def __init__(self, day: date = date(2026, 10, 5)) -> None:
        self._day = day

    def now(self) -> datetime:
        return datetime(self._day.year, self._day.month, self._day.day, tzinfo=UTC)

    def today(self) -> date:
        return self._day


class FakeHttp:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, *, accept: str | None = None) -> bytes:
        raise NotImplementedError

    def get_json(self, url: str) -> Any:
        self.urls.append(url)
        return self.payload


def test_greenhouse_filters_title_location_and_age() -> None:
    http = FakeHttp(
        {
            "jobs": [
                {
                    "title": "Engineering Manager, Payments",
                    "absolute_url": "https://x/1",
                    "location": {"name": "Seattle, WA"},
                    "first_published": "2026-10-01T00:00:00Z",
                },
                {
                    "title": "Software Engineer",
                    "absolute_url": "https://x/2",
                    "location": {"name": "Seattle, WA"},
                    "first_published": "2026-10-01T00:00:00Z",
                },
                {
                    "title": "Engineering Manager, Infra",
                    "absolute_url": "https://x/3",
                    "location": {"name": "London"},
                    "first_published": "2026-10-02T00:00:00Z",
                },
                {
                    "title": "Engineering Manager, Old",
                    "absolute_url": "https://x/4",
                    "location": {"name": "Seattle"},
                    "first_published": "2026-01-01T00:00:00Z",
                },
            ]
        }
    )
    source = JobBoardSource(
        "Stripe",
        "greenhouse",
        "stripe",
        http,
        FixedClock(),
        title_patterns=EM,
        location_patterns=["seattle"],
    )
    items = source.collect()
    assert [item.url for item in items] == ["https://x/1"]
    assert http.urls == ["https://boards-api.greenhouse.io/v1/boards/stripe/jobs"]


def test_lever_and_ashby_shapes_are_normalized() -> None:
    lever = FakeHttp(
        [
            {
                "text": "Software Development Manager",
                "hostedUrl": "https://l/1",
                "categories": {"location": "Remote"},
                "createdAt": 1791158400000,
            }
        ]
    )
    assert (
        JobBoardSource("L", "lever", "co", lever, FixedClock(), title_patterns=EM)
        .collect()[0]
        .summary
        == "Remote"
    )
    ashby = FakeHttp(
        {
            "jobs": [
                {
                    "title": "Engineering Manager",
                    "jobUrl": "https://a/1",
                    "location": "NYC",
                    "isRemote": True,
                    "publishedAt": "2026-10-04T10:00:00.000+00:00",
                },
                {"title": "Engineering Manager", "jobUrl": "https://a/2", "isListed": False},
            ]
        }
    )
    items = JobBoardSource("A", "ashby", "co", ashby, FixedClock(), title_patterns=EM).collect()
    assert [(item.url, item.summary) for item in items] == [("https://a/1", "NYC (remote)")]


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        JobBoardSource("X", "workday", "co", FakeHttp({}), FixedClock(), title_patterns=EM)


def test_question_bank_rotates_daily_and_cites_company_page() -> None:
    bank = ROOT / "catalog/interview_bank.yaml"
    first = QuestionBankSource("bank", bank, FixedClock(), companies=["amazon", "google"]).collect()
    second = QuestionBankSource(
        "bank", bank, FixedClock(date(2026, 10, 6)), companies=["amazon", "google"]
    ).collect()
    assert len(first) == 2
    assert first[0].url.startswith("https://www.amazon.jobs/")
    assert first[0].title != second[0].title
    assert first[0].dedupe_key and first[0].dedupe_key.startswith("2026-10-05:amazon:")


def test_question_bank_rejects_unknown_company() -> None:
    bank = ROOT / "catalog/interview_bank.yaml"
    with pytest.raises(ConfigError, match="not in question bank"):
        QuestionBankSource("bank", bank, FixedClock(), companies=["nope"]).collect()


def test_bank_ids_are_unique_and_rows_complete() -> None:
    companies = load_yaml(ROOT / "catalog/interview_bank.yaml")["companies"]
    for key, company in companies.items():
        assert company["reference_url"].startswith("https://"), key
        ids = [row["id"] for row in company["questions"]]
        assert len(ids) == len(set(ids)), key
        assert all(row["question"] and row["signal"] for row in company["questions"])


def test_wizard_answers_customize_sdm_sources() -> None:
    sources = load_yaml(ROOT / "config/sources.example.yaml")
    _customize_sources(
        sources, {"job_locations": ["Seattle", "Remote"], "target_companies": ["Amazon", "Netflix"]}
    )
    collectors = sources["collectors"]
    boards = [row for row in collectors["sdm_jobs"]["sources"] if row["type"] == "job_board"]
    assert boards and all(row["location_patterns"] == ["Seattle", "Remote"] for row in boards)
    assert collectors["interview_drill"]["sources"][0]["companies"] == ["amazon", "netflix"]
    hosts = sources["http"]["allowed_hosts"]
    assert {"boards-api.greenhouse.io", "api.ashbyhq.com", "api.lever.co"} <= set(hosts)


def test_invalid_location_pattern_is_a_config_error() -> None:
    from saathi.jobs.sources import build_source

    row = {
        "name": "X",
        "type": "job_board",
        "provider": "greenhouse",
        "board": "x",
        "title_patterns": EM,
        "location_patterns": ["("],
    }
    with pytest.raises(ConfigError, match="X:"):
        build_source(row, FakeHttp({}), None, FixedClock())  # type: ignore[arg-type]
