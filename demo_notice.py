"""Separate local component UI; never imports the service-backed app."""

import json

import streamlit as st

from demo_replay import PDF_PATH, SCENARIOS, fixture_responses, run_demo
from notice_helpers import translated_notice_or_original


st.set_page_config(page_title="School Buddy - synthetic component demo", page_icon="📄", layout="wide")
st.title("School Buddy | Synthetic component replay")
st.warning("SYNTHETIC INPUT · FIXTURE MODEL RESPONSES · S3 / EMBEDDINGS / DATABASE MOCKED")
st.caption("A separate demo UI reusing real PDF parsing and notice helpers. This does not prove live inference, pgvector retrieval, or production app operation.")

left, right = st.columns([1, 2])
with left:
    st.subheader("Reproduce a scenario")
    scenario = st.selectbox("Injected scenario", SCENARIOS, key="demo_scenario")
    fixtures = fixture_responses()
    language = st.selectbox("Handwritten fixture response language", list(fixtures["translations"]), key="demo_language")
    if st.button("Process synthetic PDF", type="primary", key="demo_run"):
        st.session_state["demo_snapshot"] = run_demo(scenario)
    if st.button("Reset demo", key="demo_reset"):
        st.session_state.pop("demo_snapshot", None)
    st.download_button("Download synthetic input PDF", PDF_PATH.read_bytes(), "synthetic-notice.pdf", "application/pdf")
    st.caption("Only the supplied fictional fixture is processed. No arbitrary/student upload is accepted.")

with right:
    st.subheader("Observed helper results")
    snapshot = st.session_state.get("demo_snapshot")
    if snapshot is None:
        st.info("No synthetic notice processed yet. Choose a scenario and process the provided PDF.")
    else:
        result = snapshot["result"]
        st.caption(f"Processed scenario: {snapshot['scenario']}")
        a, b, c = st.columns(3)
        a.metric("Raw recorded in memory", "Yes" if result["raw_saved"] else "No")
        b.metric("Summary recorded in memory", "Yes" if result["summary_saved"] else "No")
        c.metric("Committed stub chunks", result["indexed_chunks"])
        if result["indexed"]:
            st.success("Local replay complete: mock commit returned before indexing was marked successful.")
        elif result["summary_saved"]:
            st.warning("Summary retained in memory; mock indexing is incomplete.")
        else:
            st.error(f"Replay stopped at {result['failed_stage']} ({result['error_code']}).")
        if snapshot["notice"]:
            notice = translated_notice_or_original(snapshot["notice"], fixtures["translations"][language])
            st.caption("Notice card: handwritten response fixture; shape validation is real, translation quality is not measured.")
            st.subheader(notice["title"])
            st.write(notice["summary"])
            st.json(notice["details"])
        with st.expander("Inspect real extraction, state flags and mocked call trace", expanded=True):
            st.text(snapshot["extracted_text"] or "No text available after this injected failure.")
            st.json({"result": result, "stored_keys": snapshot["stored_keys"], "fixture_sha256": snapshot["fixture_sha256"]})
            st.dataframe(snapshot["trace"], hide_index=True, width="stretch")
        st.download_button("Download reproducible replay JSON", json.dumps(snapshot, ensure_ascii=False, indent=2),
                           f"synthetic-{snapshot['scenario']}.json", "application/json")

st.divider()
st.caption("Real: PDF parser, JSON/translation-shape validation, chunking and ingestion/cleanup control flow. Mocked: model content, cloud storage, vector generation and DB transaction calls. No service credentials are needed.")
