# Engineering-manager (SDM/EM) job search and interview prep

Two capabilities and one skill turn Saathi into an EM job-search and interview coach.

| Piece | What it does |
|---|---|
| `sdm_jobs` capability | Weekdays: new EM/SDM roles from Greenhouse, Lever, and Ashby public board APIs (no scraping, no login), plus big-tech hiring news via Google News. Only unseen postings are reported. |
| `interview_prep` capability | Daily: one question per target company from `catalog/interview_bank.yaml`, with the value it tests, what a strong answer shows, a STAR skeleton, and follow-up probes. |
| `skills/mock-interview` | Live, company-specific mock interviews in the owner chat with bar-raiser-style follow-ups and rubric scores. |

## Enable

In `saathi init`, choose `sdm_jobs` and `interview_prep`. It asks for job location patterns (case-insensitive regexes; empty = all; a US-only example is in `config/sources.example.yaml`) and
target companies from the bank (`amazon`, `google`, `meta`, `microsoft`, `apple`, `netflix`, `startup`).
Answers-file keys: `job_locations`, `target_companies`.

Add companies by appending a `job_board` source with `provider: greenhouse|lever|ashby` and the board
name from the company's careers URL (e.g. `boards.greenhouse.io/<board>`). Hosts are already allowlisted.
Big-tech careers sites have no public board API; run JobSpy by hand on your own machine for those
(`catalog/addons.yaml` -> `jobspy`).

Install the mock-interview skill for Hermes (the bank path assumes the repo is at `~/saathi`):

```bash
mkdir -p ~/.hermes/skills && cp -R ~/saathi/skills/mock-interview ~/.hermes/skills/
```

Then in the owner chat: "mock amazon", "mock google, senior EM, 2 questions". Session scores are appended
to `state/interview-log.md` (titles and scores only).

Extend the bank: add companies or questions to `catalog/interview_bank.yaml`; each question needs a unique
`id`, `question`, `signal`, and `values`. `reference_url` must be the company's own HTTPS page.
