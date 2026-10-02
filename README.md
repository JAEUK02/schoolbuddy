# School Buddy: integrated notice app

**A team hackathon prototype for reading Korean school notices and asking follow-up questions.** This `model_optimization` branch contains the representative OCR + RAG app and its follow-up reliability improvements.

**Start with [`test_jaeuk.py`](test_jaeuk.py).** For the wider project and contribution history, see the [main-branch overview](https://github.com/JAEUK02/schoolbuddy/blob/main/README.md) and [code/branch map](https://github.com/JAEUK02/schoolbuddy/blob/main/docs/code-map.md).

## Review and setup path

| Review goal | Where to look |
| --- | --- |
| Integrated upload, dashboard, translation, retrieval, and chat | [`test_jaeuk.py`](test_jaeuk.py) |
| JSON validation, unchanged text windows, partial saves, and DB cleanup | [`notice_helpers.py`](notice_helpers.py) |
| Existing-resource configuration, dependencies, launch command, and limits | [Setup and offline verification](docs/notice-development.md) |
| Offline regression cases | [`tests/test_notice_helpers.py`](tests/test_notice_helpers.py) |
| App dependencies and placeholder settings | [`requirements-notice.txt`](requirements-notice.txt) · [`.env.example`](.env.example) |

The integrated entry command is `streamlit run test_jaeuk.py`, after following the setup guide. Running the app can invoke paid models and write to configured S3/DB resources. The offline tests below need no service credentials or service SDK imports.

## Offline checks

From this branch's root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

[`pytest.ini`](pytest.ini) restricts collection to `tests/`; it does not collect the executable app or older root-level experiments named `test_*.py`. A standard-library alternative is `python -m unittest discover -s tests -v`. The [setup guide](docs/notice-development.md#offline-regression-suite) also lists scoped lint and compile commands.

The reliability pass verified **23 offline tests / 40 subtests** using mocked S3, DB, embedding, and model boundaries with socket connections blocked. The [successful PR CI run](https://github.com/JAEUK02/schoolbuddy/actions/runs/36954722132) tested the reliability change; the exact merge commit was checked locally. Current CI triggers cover improvement-branch pushes and PRs into `model_optimization`. These results do not establish live service operation.

## Implemented flow

| Stage | Representative behavior |
| --- | --- |
| Read notices | Gemini 2.5 Flash reads JPEG/PNG images; `pypdf` extracts PDF text. |
| Store and summarize | S3 keeps raw uploads under `raw/` and validated notice JSON under `analysis/`. |
| Translate | Korean, English, Vietnamese, and Chinese choices; JSON translation with a 3,600-second cache and validated-original fallback. |
| Retrieve and answer | Bedrock Titan v1 embeds 1,000-character windows at an 800-character stride; PostgreSQL/pgvector L2 search retrieves 10 chunks for Gemini document-context Q&A. |

AWS clients use `us-west-2`. Existing S3 resources and a compatible PostgreSQL/pgvector schema must be configured separately; the source does not establish a deployed RDS/Lambda/IAM/VPC architecture.

## Contribution and reliability history

This is a public fork of the team's [xianiax02/schoolbuddy](https://github.com/xianiax02/schoolbuddy). [JAEUK02's addition commit `ab3f202`](https://github.com/JAEUK02/schoolbuddy/commit/ab3f202c9e1f62416e17991163bf95d8fd2b82e3) records the original integrated hackathon snapshot. Shared team variants and their histories are described in the main code map; that addition commit alone does not assign authorship of every shared feature.

[Merged PR #1](https://github.com/JAEUK02/schoolbuddy/pull/1) adds four-language empty states, notice JSON validation, translation fallback, separate raw/summary/indexing progress, and rollback/resource cleanup. Indexing success requires a completed commit. The revoked embedded credential fallback was removed from the current `test_jaeuk.py`; its configuration example contains placeholders only.

## Historical education-guide variants

The older [`schoolbuddy.py`](schoolbuddy.py) and [`schoolbuddy_ver2.py`](schoolbuddy_ver2.py) are separate guide-context conversation variants. Their `load_education_guide()` and `search_education_content()` functions provide structured guide snippets and keyword lookup alongside document search. Illustrative topics include school notices, parent counselling, supplies, meals, after-school activities, school violence, and support for multicultural families.

The old `streamlit run schoolbuddy.py` command belongs to that variant. [`test_guide.py`](test_guide.py) is a separate console experiment, not the current offline regression suite. The guide PDF named in the previous README, `교육부 학부모가이드.pdf`, is not bundled under that filename on this branch. The representative app reads uploaded notices rather than requiring that guide file.

The earlier PDF-OCR roadmap should be read in this variant context. The integrated app already implements image OCR and PDF text extraction; scanned-PDF OCR remains a limit, and no calendar/notification feature is asserted here.

## Status and limits

- This remains an educational team prototype. The reliability patch was not deployed; live AWS/Gemini/DB integration, the Streamlit interface, and full end-to-end operation remain unverified.
- Scanned PDFs have no OCR fallback. Some UI strings remain untranslated despite four language choices.
- Q&A receives retrieved context but does not enforce citations or refusal without relevant context. Accuracy, latency, user impact, and production readiness are separate evaluation tasks.

See [setup and limits](docs/notice-development.md) before attempting service-backed execution.
