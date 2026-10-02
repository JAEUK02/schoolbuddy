# School Buddy: code and experiment map

This map helps reviewers follow the public repository without assuming that similarly named files or branches are one deployable application. Original hackathon snapshot and current reliability improvements reviewed: 2026-10-02. [Back to project overview](../README.md).

## A short review path

1. Read the [project overview](../README.md) for the problem and overall flow.
2. Inspect the [current `test_jaeuk.py`](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/test_jaeuk.py), [helper](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/notice_helpers.py), and [setup/limits guide](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/docs/notice-development.md) for the integrated workflow with reliability improvements.
3. Inspect the [original hackathon snapshot](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py) for upload → extraction → JSON dashboard → embeddings → document-context Q&A before that follow-up patch.
4. Open [JAEUK02's addition commit](https://github.com/JAEUK02/schoolbuddy/commit/ab3f202c9e1f62416e17991163bf95d8fd2b82e3), then the [team variant](https://github.com/JAEUK02/schoolbuddy/blob/dec67805a2b6dc0978dec7397761b284f1d41f7c/schoolbuddy_ver2.py), to understand provenance.
5. Compare the [`main` FAQ prototype](https://github.com/JAEUK02/schoolbuddy/blob/f6bb88dd4aa598f6e716c56c9531dd46b82d7f67/app.py) if you want to see the simpler prompt and streaming interaction.

## Current reliability improvement

[PR #1](https://github.com/JAEUK02/schoolbuddy/pull/1) is merged into `model_optimization`. The [current app](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/test_jaeuk.py) uses an [import-safe helper](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/notice_helpers.py) for validated notice JSON, unchanged 1,000-character/800-stride chunking, and ingestion/DB cleanup. It distinguishes raw save, summary save, and committed indexing; missing DB no longer reports indexing complete, and all four languages have empty-state messages. The revoked embedded key fallback has been removed from this current entry point.

The [offline tests](https://github.com/JAEUK02/schoolbuddy/tree/model_optimization/tests) passed **23 tests / 40 subtests** with network-blocked mocks, and push/PR CI passed. The exact merged tree was also tested locally. These checks do not establish live AWS/Gemini/DB integration or Streamlit end-to-end operation. No deployment was performed. See the [current setup and limits](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/docs/notice-development.md) for placeholders, dependency scope, partial-save behavior, and remaining limits.

## Locate the representative flow

All line references below point to the original hackathon snapshot at `ab3f202c9e1f62416e17991163bf95d8fd2b82e3`. They preserve historical evidence and are not line numbers for the current refactored app/helper; use the current branch links above for that version.

| Question | Source location | What to look for |
| --- | --- | --- |
| Which services are configured? | [`test_jaeuk.py`, lines 24–45](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L24-L45) | Gemini model, `us-west-2`, Titan embeddings, environment-based DB configuration |
| How are summaries translated? | [Lines 51–78](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L51-L78) | JSON-value translation, original-content fallback, cache TTL 3,600 seconds |
| How do language choices and uploads enter the flow? | [Lines 119–176](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L119-L176) | Four language options and PDF/image upload control |
| How is a notice processed? | [Lines 178–225](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L178-L225) | Raw S3 storage, OCR versus PDF extraction, notice JSON, 1,000-character chunks / stride 800 / overlap 200, embeddings, DB insertion |
| How does the dashboard load content? | [Lines 229–255](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L229-L255) | S3 `analysis/` JSON, recent notice cards, on-demand translation |
| How does Q&A retrieve information? | [Lines 257–282](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L257-L282) | Titan query embedding, pgvector `<->`, top 10 chunks, Gemini prompt with context |
| How are external programs handled? | [Lines 80–114](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L80-L114) and [284–299](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py#L284-L299) | Cached Danuri listing fetch, link navigation, and optional interaction logging |

## File and version map

This table describes the original fixed snapshots. Current reliability changes are linked separately above.

| Branch and file | Purpose | Important distinction |
| --- | --- | --- |
| [`main/app.py`](https://github.com/JAEUK02/schoolbuddy/blob/f6bb88dd4aa598f6e716c56c9531dd46b82d7f67/app.py) | FAQ buttons, optional user context, streamed answers, three-step explanations | Nova Lite in `us-east-1`; no upload or retrieval pipeline |
| [`model_optimization/test_jaeuk.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_jaeuk.py) | Integrated OCR, JSON, translation, retrieval, and chat experiment | Gemini + Titan in `us-west-2`; pgvector L2 top 10 |
| [`model_optimization/schoolbuddy.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/schoolbuddy.py) and [`schoolbuddy_ver2.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/schoolbuddy_ver2.py) | Bedrock/Claude conversation variants with education-guide context | Manually entered guide content and keyword selection; cosine `<=>` top 3 applies here, separately from the representative file |
| [`model_optimization/school_admin.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/school_admin.py) | Local PDF notice listing and upload UI | Writes to `school_notices/`; this version does not implement S3 ingestion |
| [`model_optimization/test_guide.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_guide.py) | Console experiment for manually entered guide topics and keyword matching | An exploratory script, separate from full-app validation |
| [`model_optimization/test_pdf.py`](https://github.com/JAEUK02/schoolbuddy/blob/ab3f202c9e1f62416e17991163bf95d8fd2b82e3/test_pdf.py) | Local PDF extraction and text-search experiment | Expects `교육부 학부모가이드.pdf`, which is absent from this branch's reviewed file tree |
| [`model-optimization`](https://github.com/JAEUK02/schoolbuddy/tree/12f08289055012d7c856bd424abdef20803f096c) | Separate `schoolbuddy.py` / `schoolbuddy_ver2.py` Bedrock variants | The hyphenated branch includes `교육부 학부모가이드.pdf`; it has a different tree from the underscore branch |
| [`feat_be/school_admin.py`](https://github.com/JAEUK02/schoolbuddy/blob/dec67805a2b6dc0978dec7397761b284f1d41f7c/school_admin.py) | Team S3/Gemini/Titan upload experiment | Different from the local-only admin file on `model_optimization` |
| [`feat_be/schoolbuddy_ver2.py`](https://github.com/JAEUK02/schoolbuddy/blob/dec67805a2b6dc0978dec7397761b284f1d41f7c/schoolbuddy_ver2.py) and [`schoolbuddy_ver3.py`](https://github.com/JAEUK02/schoolbuddy/blob/dec67805a2b6dc0978dec7397761b284f1d41f7c/schoolbuddy_ver3.py) | Integrated team variants; version 3 adds program-interaction log visualization | Share core functionality with `test_jaeuk.py`; filename versions are branch-specific |
| [`feat_be/setup_db.py`](https://github.com/JAEUK02/schoolbuddy/blob/dec67805a2b6dc0978dec7397761b284f1d41f7c/setup_db.py) | `program_logs` table setup | Does not create the `documents` vector table or pgvector extension |
| [`landingpage/index.html`](https://github.com/JAEUK02/schoolbuddy/blob/b2151699f1ec314a5aea13c693f6f9b8db345aa3/index.html) | Static project brief describing the intended workflow | A specification document; planned behavior needs implementation evidence from the Python variants |
| [`seowoo-dot-patch-1/app.py`](https://github.com/JAEUK02/schoolbuddy/blob/a75e92f723f57f2ceb9896db080aca171b19e4ba/app.py) | FAQ-app revision | Related to `main`; not the integrated document-processing app |

## Contribution and provenance

The fork's [upstream team repository](https://github.com/xianiax02/schoolbuddy) and its branch histories provide the wider implementation context.

- JAEUK02's [commit `ab3f202`](https://github.com/JAEUK02/schoolbuddy/commit/ab3f202c9e1f62416e17991163bf95d8fd2b82e3) adds `test_jaeuk.py` to the public fork.
- The corresponding integrated team variant has a [file history on `feat_be`](https://github.com/JAEUK02/schoolbuddy/commits/feat_be/schoolbuddy_ver2.py). Its shared structure matters when attributing the whole pipeline.
- The [initial FAQ app history](https://github.com/JAEUK02/schoolbuddy/commits/main/app.py) records the upstream contributors to `main`.
- The [education-guide variant history](https://github.com/JAEUK02/schoolbuddy/commits/model_optimization/schoolbuddy.py) records a separate experiment.

Use these histories together to distinguish the code added to this fork from the shared team implementation. The addition commit alone does not allocate ownership of every shared feature.

## Reproduction boundaries

`main/requirements.txt` belongs to the Nova Lite app. The integrated experiment imports additional libraries and needs independently configured S3 and PostgreSQL resources. The current branch has an [import-derived dependency list](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/requirements-notice.txt) and [setup guide](https://github.com/JAEUK02/schoolbuddy/blob/model_optimization/docs/notice-development.md), but no validated production dependency lock or complete database migration set.

To inspect the integrated experiment, select the `model_optimization` branch or use a separate checkout. Its entry command is `streamlit run test_jaeuk.py` from that branch's root.

The imports require Streamlit, boto3, psycopg2, requests, `google-generativeai`, `python-dotenv`, Beautiful Soup, `langchain-aws`, and pypdf with mutually compatible versions. The original `lambda/requirements.txt` supplies only part of that set; current `requirements-notice.txt` lists this entry point's imports without claiming a tested live SDK combination. The branch does not include a complete deployment recipe or documents-table migration; `feat_be/setup_db.py` creates only `program_logs`.

The representative file expects:

| Resource | Expected use |
| --- | --- |
| Gemini credentials | Required `GENAI_API_KEY` from your own local environment; the revoked fallback is removed from the current representative entry point |
| AWS access | S3 and Titan embedding calls in `us-west-2` |
| S3 | `BUCKET_NAME`, with `raw/` for uploaded files and `analysis/` for generated JSON |
| PostgreSQL + pgvector | `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`; `documents` needs content, embedding, and metadata columns compatible with the code |
| Interaction log table | `program_logs` with user language, title, link, and timestamp fields |

In the original `ab3f202` snapshot, a successful upload message could appear without vector insertion, and empty-dashboard handling referenced a missing `no_data` translation entry. Merged PR #1 fixes both in the current branch and adds failure-path/JSON tests. Historical source links remain fixed to document that progression; they do not describe the current version's error handling.

Additional evaluation and implementation limits:

- Image OCR and PDF extraction use separate paths. Scanned PDFs have no OCR fallback in the representative file.
- Language selection and JSON translation are implemented; several interface strings remain mixed or untranslated.
- The representative chat prompt includes retrieved context, but source citations and no-context refusal are not enforced.
- Accuracy, retrieval quality, latency, and cost improvements have no published measured evaluation here. The cache TTL is an implementation setting, not evidence of a speedup.
- Calendar integration and notifications are future ideas, separate from the recorded implementation.

Cloud access, dependency resolution, and a complete application run have not been revalidated during this documentation review.

No live cloud calls, database writes, credential tests, or end-to-end application runs were performed while preparing this map.
