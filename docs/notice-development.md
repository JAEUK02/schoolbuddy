# Representative notice app: setup and offline verification

This guide covers `test_jaeuk.py` on the `model_optimization` branch and its reliability improvement. Other branch entry points have different dependencies and behavior. The [main-branch project overview](https://github.com/JAEUK02/schoolbuddy/blob/main/README.md) and [code map](https://github.com/JAEUK02/schoolbuddy/blob/main/docs/code-map.md) remain available.

## What the code establishes

The app runs synchronously in Streamlit. Gemini `models/gemini-2.5-flash` reads images and produces notice JSON; `pypdf` extracts text from PDFs. S3 stores `raw/{file_name}` and `analysis/{file_name}.json`. Bedrock Titan `amazon.titan-embed-text-v1` embeds 1,000-character windows at an 800-character stride. The code connects to PostgreSQL and uses pgvector L2 (`<->`) retrieval with `LIMIT 10`.

Both AWS clients use `us-west-2`. These model IDs, region, S3 prefixes, SQL table/column names, chunk boundaries, and retrieval policy are unchanged by this improvement. The source does not establish RDS hosting, Lambda handlers, an IAM deployment design, or a VPC architecture.

## Configuration and resources

Copy `.env.example` to a local `.env` and replace its placeholders. `.env` files are ignored by Git. `GENAI_API_KEY` is required; the app stops with a setup message when absent and has no embedded fallback credential.

| Setting | Used for |
| --- | --- |
| `GENAI_API_KEY` | Existing Gemini API credential |
| `BUCKET_NAME` | Existing S3 bucket for raw uploads and analysis JSON |
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Existing PostgreSQL connection, port 5432 and a 3-second connection timeout |
| Optional `AWS_PROFILE` | An existing local profile in the standard AWS SDK credential chain |

The code passes no access-key literals to boto3. Use an existing authorized profile or another SDK-supported credential provider. The `.env` example creates no credentials or resources.

The app expects an existing database with `documents` columns `content`, `embedding`, `metadata`, and `program_logs` columns `user_lang`, `program_title`, `program_link`. pgvector support and a compatible embedding column are required by the SQL. No schema definition, dimension migration, or database provisioning is included; verify compatibility with the existing schema rather than guessing it.

`requirements-notice.txt` lists the packages corresponding to this entry point's imports, including PDF extraction. It is not a tested production lockfile. The service SDK combination and live setup have not been exercised in this change.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notice.txt
# Configure existing credentials/resources before choosing to run the app.
streamlit run test_jaeuk.py
```

Running the app can make paid model requests, read/write S3 objects and database rows, and contact the public program site. These operations are outside the offline validation below and were not performed for this change.

## Failure and partial-progress behavior

- Empty/missing S3 `Contents`, or no JSON notice objects, displays an empty-state message in each of the four languages.
- Raw upload, summary storage, and database indexing have separate progress flags. A failed raw upload blocks extraction, model analysis, and database calls. A failed summary upload blocks indexing.
- Notice JSON must be an object with nonempty string `title`/`summary`. Missing or null `details` becomes an empty object; array/scalar shapes are rejected. Unknown fields are retained. A missing date remains missing; validation does not infer a date or verify model factual accuracy.
- Translation accepts string changes only when all keys, nesting, list lengths, and nonstring values match the validated original. Invalid JSON, changed shape, or a translation exception falls back to that original notice.
- Database indexing is marked successful only after `commit()` returns. Missing DB or an embedding/insert/commit failure leaves the saved summary available but reports indexing incomplete. Failures roll back the DB transaction and close both cursor and connection; cleanup is attempted even if rollback or cursor close fails.
- Already stored S3 objects are retained. No compensating delete or automatic migration occurs. Retrying still uses the original object keys and insert behavior; duplicate-index prevention is not implemented here.
- Chat retrieval and program logging use the same resource cleanup. Missing-DB chat answer behavior and source-citation/refusal policy are unchanged.

## Offline regression suite

The helper imports only Python's standard library, reads no environment configuration, and creates no service client. Tests inject mock S3/DB/embedding/model objects and block socket connections. Selected app functions and language literals are extracted with `ast`; importing the executable Streamlit app or loading `.env` is unnecessary.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m unittest discover -s tests -v
ruff check --select E4,E9,F,E722 test_jaeuk.py notice_helpers.py notice_inputs.py demo_notice.py demo_replay.py tests tools
python -m compileall -q test_jaeuk.py notice_helpers.py notice_inputs.py demo_notice.py demo_replay.py tests tools
```

`pytest.ini` restricts discovery to `tests/`, so the app named `test_jaeuk.py` and the legacy `test_guide.py`/`test_pdf.py` entry points are not collected. The suite covers empty S3 listings, four language messages, partial saves, missing DB, raw/summary S3 failure ordering, JSON shapes, unknown fields, translation fallback, Unicode chunk boundaries, parameterized inserts, commit-once success, and rollback/cleanup failures.

The `Notice offline checks` workflow repeats pytest, scoped lint, and compile on Python 3.11 for the reliability-improvement branch and relevant pull requests into `model_optimization`. It installs the local parser, Streamlit and test dependencies, passes no service credentials, and runs tests with an empty environment except `PATH` and the pytest plugin flag. Streamlit AppTest runs the separate synthetic component UI; CI does not deploy or execute the service-backed app.

Live permissions, real Gemini/Bedrock responses, actual schema/vector adaptation, transaction behavior on a deployed server, service-backed Streamlit rendering, and end-to-end application operation remain unverified. The [separate synthetic demo](synthetic-demo.md) adds shared PDF parsing, injected services, local UI tests and actual browser captures; those results apply only to that demo. No paid call, deployment, AWS resource change, real database access, or production data mutation was made.
