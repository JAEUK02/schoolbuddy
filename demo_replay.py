"""Synthetic component replay. No service SDK, environment or credential access."""

import argparse
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

from notice_helpers import ingest_notice, recent_analysis_objects
from notice_inputs import extract_pdf_text


ROOT = Path(__file__).resolve().parent
PDF_PATH = ROOT / "fixtures" / "synthetic-notice.pdf"
RESPONSES_PATH = ROOT / "fixtures" / "synthetic-responses.json"
SCENARIOS = (
    "success", "missing_db", "raw_save_failure", "summary_save_failure",
    "invalid_json", "embedding_failure", "commit_failure", "empty_text",
)
INSERT_SQL = "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s, %s)"


class StorageStub:
    """In-memory bytes; these operations never contact S3."""

    def __init__(self, scenario, trace):
        self.scenario, self.trace, self.objects = scenario, trace, {}

    def put_object(self, *, Bucket, Key, Body):
        self.trace.append({"operation": "storage.stub.put", "key": Key})
        stage = "raw_save_failure" if Key.startswith("raw/") else "summary_save_failure"
        if self.scenario == stage:
            raise RuntimeError("Injected storage failure")
        self.objects[Key] = Body.encode() if isinstance(Body, str) else bytes(Body)

    def list_objects_v2(self, *, Bucket, Prefix):
        objects = [{"Key": key, "LastModified": "2000-01-01T00:00:00Z"}
                   for key in self.objects if key.startswith(Prefix)]
        return {"Contents": objects} if objects else {}

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}


class CursorStub:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params):
        if sql != INSERT_SQL:
            raise AssertionError("Only the existing parameterized insert is accepted")
        text, vector, metadata = params
        self.connection.pending.append({"content": text, "vector": vector,
                                        "metadata": json.loads(metadata)})
        self.connection.trace.append({"operation": "database.stub.insert", "characters": len(text)})

    def close(self):
        self.connection.trace.append({"operation": "database.stub.cursor.close"})


class ConnectionStub:
    """Record transaction calls; no PostgreSQL or pgvector engine is emulated."""

    def __init__(self, scenario, trace, rows):
        self.scenario, self.trace, self.rows, self.pending = scenario, trace, rows, []

    def cursor(self):
        return CursorStub(self)

    def commit(self):
        self.trace.append({"operation": "database.stub.commit"})
        if self.scenario == "commit_failure":
            raise RuntimeError("Injected commit failure")
        self.rows.extend(self.pending)
        self.pending = []

    def rollback(self):
        self.trace.append({"operation": "database.stub.rollback"})
        self.pending = []

    def close(self):
        self.trace.append({"operation": "database.stub.connection.close"})


class EmbeddingStub:
    """Four-dimensional bookkeeping vectors; not Titan output or quality scores."""

    def __init__(self, scenario, trace):
        self.scenario, self.trace = scenario, trace

    def embed_query(self, text):
        self.trace.append({"operation": "embedding.stub", "characters": len(text)})
        if self.scenario == "embedding_failure":
            raise RuntimeError("Injected embedding failure")
        return [float(len(text)), float(text.count("reading")), float(text.count("notebook")), 0.0]


def fixture_responses():
    return json.loads(RESPONSES_PATH.read_text(encoding="utf-8"))


def run_demo(scenario="success"):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown synthetic scenario")
    pdf_bytes = PDF_PATH.read_bytes()
    fixtures = fixture_responses()
    trace, rows = [], []
    storage = StorageStub(scenario, trace)
    extracted = []

    def extract(data, name):
        text = extract_pdf_text(data)
        extracted.append(text)
        trace.append({"operation": "pdf.real.pypdf", "characters": len(text)})
        return "" if scenario == "empty_text" else text

    def analyze(text):
        trace.append({"operation": "model.fixture.reply"})
        return "not JSON" if scenario == "invalid_json" else json.dumps(fixtures["analysis"])

    def connect():
        trace.append({"operation": "database.stub.connect"})
        return None if scenario == "missing_db" else ConnectionStub(scenario, trace, rows)

    result = ingest_notice(
        s3=storage, bucket="synthetic-local-storage", file_bytes=pdf_bytes,
        file_name="synthetic-notice.pdf", extract_text=extract, analyze_text=analyze,
        connect=connect, embeddings_factory=lambda: EmbeddingStub(scenario, trace),
    )
    objects = recent_analysis_objects(storage.list_objects_v2(
        Bucket="synthetic-local-storage", Prefix="analysis/",
    ))
    notice = None
    if objects:
        notice = json.loads(storage.get_object(
            Bucket="synthetic-local-storage", Key=objects[0]["Key"],
        )["Body"].read())
    return {
        "label": "SYNTHETIC COMPONENT REPLAY - SERVICES MOCKED",
        "fixture_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "scenario": scenario,
        "real_components": ["pypdf text extraction", "notice validation", "chunk_text",
                            "ingest_notice", "database_cursor control flow"],
        "mocked_components": ["model response", "S3 storage", "embedding vectors", "database"],
        "not_exercised": ["image OCR", "live translation/inference", "pgvector retrieval",
                          "production Streamlit entrypoint", "AWS/DB integration"],
        "result": asdict(result), "stored_keys": sorted(storage.objects),
        "extracted_text": extracted[0] if extracted else "", "notice": notice,
        "committed_stub_rows": rows, "trace": trace,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="success")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(run_demo(args.scenario), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
