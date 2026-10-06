"""Local interview question bank rotated deterministically by date."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.domain.config import ConfigError, load_yaml, require_list, require_mapping
from saathi.domain.models import Item
from saathi.domain.ports import Clock


class QuestionBankSource:
    """Pick today's practice questions for the configured target companies."""

    def __init__(
        self,
        name: str,
        path: Path,
        clock: Clock,
        *,
        companies: list[str],
        per_company: int = 1,
    ) -> None:
        self.name = name
        self._path = path
        self._clock = clock
        self._companies = companies
        self._per_company = per_company

    def collect(self) -> list[Item]:
        """Return a stable daily selection that cycles through each company's questions."""

        bank = load_yaml(self._path)
        companies = require_mapping(bank.get("companies"), "companies")
        day = self._clock.today()
        items: list[Item] = []
        for key in self._companies:
            if key not in companies:
                raise ConfigError(f"{self.name}: company not in question bank: {key}")
            company = require_mapping(companies[key], f"companies.{key}")
            questions = require_list(company.get("questions"), f"companies.{key}.questions")
            if not questions:
                continue
            start = (day.toordinal() * self._per_company) % len(questions)
            for offset in range(min(self._per_company, len(questions))):
                row = require_mapping(questions[(start + offset) % len(questions)], key)
                items.append(self._item(key, company, row, day.isoformat()))
        return items

    def _item(self, key: str, company: dict[str, Any], row: dict[str, Any], day: str) -> Item:
        signal = str(row.get("signal", ""))
        values = ", ".join(str(value) for value in row.get("values", []))
        summary = f"Assesses: {signal}" + (f" | Company values: {values}" if values else "")
        return Item(
            title=f"{company.get('name', key)}: {row.get('question', '')}",
            url=str(company.get("reference_url", "")),
            source=self.name,
            summary=summary,
            metadata={"summary_limit": 400},
            dedupe_key=f"{day}:{key}:{row.get('id', row.get('question'))}",
        )
