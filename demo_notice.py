"""Separate local component UI; never imports the service-backed app."""

import json

import streamlit as st

from demo_replay import PDF_PATH, ROOT, SCENARIOS, fixture_responses, run_demo
from notice_helpers import translated_notice_or_original


st.set_page_config(page_title="School Buddy - synthetic component demo", page_icon="📘", layout="wide")
st.html(ROOT / "demo_style.css")
st.html('''<header class="buddy-hero">
  <div class="buddy-brand">
    <span class="buddy-book" aria-hidden="true">📘</span>
    <span>SCHOOL BUDDY · LOCAL DEMO</span>
  </div>
  <h1>A little clarity for school days.</h1>
  <p>Explore a fictional school notice, one simple step at a time.</p>
</header>''')
with st.container(key="demo_disclosure"):
    st.info("SYNTHETIC INPUT · FIXTURE MODEL RESPONSES · S3 / EMBEDDINGS / DATABASE MOCKED")
st.caption("A separate demo UI reusing real PDF parsing and notice helpers. This does not prove live inference, pgvector retrieval, or production app operation.")

left, right = st.columns([1, 1.7], gap="large")
with left, st.container(border=True, key="demo_controls"):
    st.subheader("Try a school notice")
    st.caption("Start with success. Then explore how partial failures are reported.")
    scenario = st.selectbox("Injected scenario", SCENARIOS, key="demo_scenario")
    fixtures = fixture_responses()
    language = st.selectbox("Handwritten fixture response language", list(fixtures["translations"]), key="demo_language")
    if st.button("Process synthetic PDF", type="primary", key="demo_run", width="stretch"):
        st.session_state["demo_snapshot"] = run_demo(scenario)
    if st.button("Reset demo", key="demo_reset"):
        st.session_state.pop("demo_snapshot", None)
    st.download_button("Download synthetic input PDF", PDF_PATH.read_bytes(), "synthetic-notice.pdf", "application/pdf")
    st.caption("Only the supplied fictional fixture is processed. No arbitrary/student upload is accepted.")

with right, st.container(border=True, key="demo_results"):
    st.subheader("Your notice, at a glance")
    snapshot = st.session_state.get("demo_snapshot")
    if snapshot is None:
        st.info("No synthetic notice processed yet. Choose a scenario and process the provided PDF.")
    else:
        result = snapshot["result"]
        st.caption(f"Processed scenario: {snapshot['scenario']}")
        a, b, c = st.columns(3)
        a.metric("Raw in memory", "Yes" if result["raw_saved"] else "No")
        b.metric("Summary in memory", "Yes" if result["summary_saved"] else "No")
        c.metric("Committed stub chunks", result["indexed_chunks"])
        if result["indexed"]:
            st.success("Local replay complete: mock commit returned before indexing was marked successful.")
        elif result["summary_saved"]:
            st.warning("Summary retained in memory; mock indexing is incomplete.")
        else:
            st.error(f"Replay stopped at {result['failed_stage']} ({result['error_code']}).")
        if snapshot["notice"]:
            notice = translated_notice_or_original(snapshot["notice"], fixtures["translations"][language])
            with st.container(border=True, key="demo_notice_card"):
                st.caption("Handwritten response fixture · Translation quality is not measured")
                st.subheader(notice["title"])
                st.write(notice["summary"])
                date_time, place_action = st.columns(2)
                with date_time:
                    st.caption("DATE & TIME")
                    st.write(f"{notice['details']['date']} · {notice['details']['time']}")
                with place_action:
                    st.caption("PLACE & PREPARATION")
                    st.write(f"{notice['details']['place']} · {notice['details']['action']}")
        with st.expander("Inspect real extraction, state flags and mocked call trace", expanded=False):
            st.text(snapshot["extracted_text"] or "No text available after this injected failure.")
            st.json({"result": result, "notice": snapshot["notice"], "stored_keys": snapshot["stored_keys"], "fixture_sha256": snapshot["fixture_sha256"]})
            st.dataframe(snapshot["trace"], hide_index=True, width="stretch")
        st.download_button("Download reproducible replay JSON", json.dumps(snapshot, ensure_ascii=False, indent=2),
                           f"synthetic-{snapshot['scenario']}.json", "application/json")

st.divider()
st.caption("Real: PDF parser, JSON/translation-shape validation, chunking and ingestion/cleanup control flow. Mocked: model content, cloud storage, vector generation and DB transaction calls. No service credentials are needed.")
