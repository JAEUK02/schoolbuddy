# Synthetic notice component demo

Try one fictional PDF locally without AWS, Gemini, PostgreSQL or credentials. This separate Streamlit entrypoint exercises the integrated experiment's real PDF parser and notice helpers with explicit fixtures at every service boundary.

**The input is synthetic; model responses are handwritten; S3, embeddings and database calls are mocked.** Screenshots show a local component replay. They do not establish production app operation, model accuracy or live RAG retrieval.

## Run locally

From the `model_optimization` code line containing this demo, use Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-demo.txt
python -m streamlit run demo_notice.py --server.address 127.0.0.1 --server.port 8512 --server.headless true --browser.gatherUsageStats false
```

Open `http://127.0.0.1:8512`. Process the supplied PDF, inspect state flags and the call trace, change the handwritten response language, and reset. Changing the scenario selector does not process anything until **Process synthetic PDF** is clicked. The result identifies its processed scenario.

No `.env` or service keys are needed. This entrypoint does not import `test_jaeuk.py`, `boto3`, `psycopg2`, Gemini or Bedrock clients. Objects and rows exist only within each replay's Python memory. There is no arbitrary file upload, external program feed or chat panel.

For a UI-free replay, only `pypdf` is required:

```bash
python -m pip install pypdf==6.19.0
python demo_replay.py --scenario success --output /tmp/synthetic-success.json
python demo_replay.py --scenario missing_db --output /tmp/synthetic-missing-db.json
```

## What runs and what is simulated

| Boundary | This demo |
| --- | --- |
| Text PDF extraction | Actual `pypdf` in [`notice_inputs.py`](../notice_inputs.py), shared with the integrated app's PDF branch. The image OCR path is unchanged and not run. |
| Ingestion and JSON validation | Actual [`ingest_notice` and `validate_notice`](../notice_helpers.py). Unknown fields remain; malformed responses stop before summary storage/indexing. |
| Chunking and transaction orchestration | Actual 1,000-character windows at an 800-character stride, parameterized insertion arguments, commit/rollback/close control flow. The connection records calls in memory; it is not a PostgreSQL engine. |
| Recent notice selection and translation shape checks | Actual `recent_analysis_objects` and `translated_notice_or_original`. Four response fixtures are handwritten, not generated translations. |
| Analysis/model response | Prewritten [`synthetic-responses.json`](../fixtures/synthetic-responses.json), or injected invalid JSON. No inference. |
| S3 | In-memory dictionary. No bucket, credentials, object permissions or persistence are exercised. |
| Embeddings | Four-dimensional bookkeeping vectors. No Titan call, vector-quality score or pgvector similarity query. |
| Interface | New [`demo_notice.py`](../demo_notice.py) only. The service-backed upload/dashboard/chat interface in `test_jaeuk.py` is not run. |

The [baseline integrated helpers](https://github.com/JAEUK02/schoolbuddy/blob/8d5959165b657dc38d972e6efd1afa3afb2d6f62/notice_helpers.py) are reused unchanged. The only service-app seam extracts its existing PDF parser into a shared function; image routing, prompts, model/region settings, storage keys and retrieval remain unchanged.

## Reproducible states

| Scenario | Raw saved | Summary saved | Indexed | Failure stage/code |
| --- | --- | --- | --- | --- |
| `success` | Yes | Yes | 2 stub chunks | None |
| `missing_db` | Yes | Yes | No | `index / db_unavailable` |
| `raw_save_failure` | No | No | No | `raw_upload / operation_failed` |
| `summary_save_failure` | Yes | No | No | `summary / operation_failed` |
| `invalid_json` | Yes | No | No | `summary / invalid_notice` |
| `embedding_failure` | Yes | Yes | No | `index / operation_failed` |
| `commit_failure` | Yes | Yes | No | `index / operation_failed` |
| `empty_text` | Yes | No | No | `extract_text / no_text` |

Every “saved” value above refers to memory. `empty_text` parses the same fixture and then injects empty output; it is not a scanned-PDF or OCR test. Committed stub rows stay empty after failures, and embedding/commit failures record rollback and resource cleanup. These observations verify the application's control flow, not a deployed database's transaction behavior.

The supplied one-page [synthetic PDF](../fixtures/synthetic-notice.pdf) contains no real school, student, contact, consultation or company material. Its text extraction produces **1,486 characters**, giving windows of **1,000 and 686 characters** with a 200-character overlap. These are fixture-specific counts, not performance results.

| Evidence | Artifact |
| --- | --- |
| Empty screen | [Actual local browser screenshot](demo-evidence/empty.png) |
| Success | [Screenshot](demo-evidence/success.png) · [replay JSON](demo-evidence/success.json) |
| DB unavailable | [Screenshot](demo-evidence/missing_db.png) · [replay JSON](demo-evidence/missing_db.json) |
| Invalid response | [Screenshot](demo-evidence/invalid_json.png) · [replay JSON](demo-evidence/invalid_json.json) |
| Capture details | [Browser/version/state record](demo-evidence/browser.json) · [evidence manifest](demo-evidence/manifest.json) |

JSON outputs are deterministic for the provided bytes and fixtures, include the PDF SHA-256, state flags, source text, stored keys and mocked trace, and can be regenerated with the CLI. Screenshots are actual local browser captures, not generated mockups; pixels can differ by browser, font and operating system.

## Validate and rebuild evidence

```bash
python -m pip install -r requirements-dev.txt
env -i PATH="$PATH" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
ruff check --select E4,E9,F,E722 test_jaeuk.py notice_helpers.py notice_inputs.py demo_notice.py demo_replay.py tests tools
python -m compileall -q test_jaeuk.py notice_helpers.py notice_inputs.py demo_notice.py demo_replay.py tests tools
```

[`test_demo_replay.py`](../tests/test_demo_replay.py) blocks socket connections and covers actual PDF extraction, app PDF/image routing, all injected failure stages, deterministic evidence, four fixture-language cards and empty/success/reset/error states through Streamlit AppTest. The earlier helper regression suite remains included. Tests do not import the service-backed app.

Local validation on Python 3.14.4 passed **32 tests / 60 subtests**, scoped lint and compilation. `python -m unittest discover -s tests -q` also passed all 32 tests. Actual Chrome 153 capture checked empty, success, missing-DB, invalid-response and reset states with no JavaScript errors. The PDF was rendered and inspected separately before use. These observations cover only the listed synthetic/offline boundaries.

Optional fixture/browser tools:

```bash
python -m pip install -r requirements-demo-tools.txt
python tools/build_demo_fixture.py
python demo_replay.py --scenario success --output docs/demo-evidence/success.json
python demo_replay.py --scenario missing_db --output docs/demo-evidence/missing_db.json
python demo_replay.py --scenario invalid_json --output docs/demo-evidence/invalid_json.json
```

With the local demo already running, `python tools/capture_demo.py` uses Playwright Chromium (install it with `python -m playwright install chromium` if needed). For an existing Mac Chrome installation, pass `--browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`. Capture creates a fresh browser context, blocks non-local page HTTP/WebSocket requests, asserts the mocked-service banner and each state, and checks for JavaScript errors. No authenticated user browser profile is used.

## Limits and next validation

Not exercised: image/scanned-PDF OCR, live Gemini analysis/translation, AWS permissions or S3 behavior, Titan embeddings, PostgreSQL schema/vector adaptation, pgvector retrieval, chat answers, external program data, service-backed Streamlit operation, deployment, accuracy, latency or user impact. No paid model call, real student record, real database write or AWS resource provisioning is involved.

Live verification would be a separate task using approved existing resources, an isolated synthetic-data database/bucket and explicit cost/call limits. Existing retrieval can read all rows in its configured database, so this component demo does not connect to a shared student-data database. See [service-backed setup and limits](notice-development.md) for the original entrypoint.
