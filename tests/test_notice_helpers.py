"""Offline regression tests: only injected mocks, no app import or credentials."""

import ast
from datetime import datetime, timezone
import json
import builtins
import os
from pathlib import Path
import runpy
import socket
import unittest
from unittest.mock import Mock, patch

from notice_helpers import (
    DatabaseUnavailableError, NoticeValidationError, chunk_text, database_cursor,
    index_notice, ingest_notice, recent_analysis_objects,
    translated_notice_or_original, validate_notice,
)


NOTICE = {"title": "학교 소식", "summary": "준비물을 확인하세요.", "details": {}}
APP = Path(__file__).resolve().parents[1] / "test_jaeuk.py"


class OfflineTest(unittest.TestCase):
    def setUp(self):
        # Fail immediately if a future test accidentally attempts network access.
        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex"):
            guard = patch(target, side_effect=AssertionError("Network is forbidden in offline tests"))
            guard.start()
            self.addCleanup(guard.stop)


class ValidationTests(OfflineTest):
    def test_invalid_json_null_array_and_bad_known_fields(self):
        for value in ("not json", "null", "[]", None, [], {}, {"title": 3, "summary": "ok"},
                      {"title": "ok", "summary": ""}, {**NOTICE, "details": []},
                      {**NOTICE, "details": {"date": 20261002}}):
            with self.subTest(value=value), self.assertRaises(NoticeValidationError):
                validate_notice(value)

    def test_details_null_is_safe_without_inventing_date(self):
        for notice in (NOTICE, {"title": "x", "summary": "y"}, {**NOTICE, "details": None}):
            self.assertEqual(validate_notice(notice)["details"], {})
            self.assertNotIn("date", validate_notice(notice)["details"])

    def test_unknown_fields_are_preserved_without_mutating_original(self):
        original = {**NOTICE, "details": {"date": None, "items": ["연필"]}, "extra": {"count": 2}}
        result = validate_notice(json.dumps(original))
        self.assertEqual(result, original)
        result["extra"]["count"] = 9
        self.assertEqual(original["extra"]["count"], 2)

    def test_translation_preserves_shape_unknown_fields_and_nonstring_values(self):
        original = {**NOTICE, "extra": {"items": ["연필"], "count": 2}}
        translated = {"title": "News", "summary": "Check supplies.", "details": {},
                      "extra": {"items": ["Pencil"], "count": 2}}
        self.assertEqual(translated_notice_or_original(original, json.dumps(translated)), translated)
        for invalid in ("null", "[]", "broken", {"title": "x", "summary": "y"},
                        {**translated, "details": None}, {**translated, "extra": {"items": [], "count": 2}},
                        {**translated, "extra": {"items": ["Pencil"], "count": 3}}):
            with self.subTest(invalid=invalid):
                self.assertEqual(translated_notice_or_original(original, invalid), original)

    def test_unicode_chunk_windows_and_boundaries_are_unchanged(self):
        for size in (0, 1, 799, 800, 801, 999, 1000, 1001, 1600, 1601, 2401):
            text = ("학교🎒中文é" * 500)[:size]
            with self.subTest(size=size):
                chunks = chunk_text(text)
                self.assertEqual(chunks, [text[i:i + 1000] for i in range(0, len(text), 800)])
                self.assertEqual(len(chunks), (size + 799) // 800)
                if size > 1000:
                    self.assertEqual(chunks[0][800:], chunks[1][:200])


class DashboardTests(OfflineTest):
    def test_empty_s3_missing_contents_and_nonjson_objects(self):
        for response in ({}, {"Contents": []}, {"Contents": None},
                         {"Contents": [{"Key": "analysis/"}, {"Key": "analysis/x.txt"}]}):
            self.assertEqual(recent_analysis_objects(response), [])

    def test_latest_three_json_objects_keep_existing_order(self):
        objects = [{"Key": f"analysis/{day}.json", "LastModified": datetime(2026, 10, day, tzinfo=timezone.utc)}
                   for day in (1, 3, 2, 4)]
        self.assertEqual([x["Key"] for x in recent_analysis_objects({"Contents": objects})],
                         ["analysis/4.json", "analysis/3.json", "analysis/2.json"])

    def test_all_four_actual_language_packs_have_empty_notice_messages(self):
        tree = ast.parse(APP.read_text())
        value = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "lang_pack" for t in node.targets))
        packs = ast.literal_eval(value)
        self.assertEqual(set(packs), {"한국어 (Korean)", "English", "Tiếng Việt", "中文"})
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(pack["no_data"].strip())


class IngestionTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.reset_dependencies()

    def reset_dependencies(self):
        self.s3 = Mock()
        self.cursor = Mock()
        self.connection = Mock()
        self.connection.cursor.return_value = self.cursor
        self.connect = Mock(return_value=self.connection)
        self.embeddings = Mock()
        self.embeddings.embed_query.return_value = [0.1, 0.2]
        self.factory = Mock(return_value=self.embeddings)
        self.extract = Mock(return_value="가" * 1601)
        self.analyze = Mock(return_value=json.dumps(NOTICE))

    def ingest(self):
        return ingest_notice(s3=self.s3, bucket="example-bucket", file_bytes=b"example",
                             file_name="notice.pdf", extract_text=self.extract,
                             analyze_text=self.analyze, connect=self.connect,
                             embeddings_factory=self.factory)

    def assert_closed(self):
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_success_commits_once_with_exact_chunks_paths_and_parameterized_sql(self):
        result = self.ingest()
        self.assertTrue(result.raw_saved and result.summary_saved and result.indexed)
        self.assertEqual(result.indexed_chunks, 3)
        self.assertIsNone(result.failed_stage)
        self.connection.commit.assert_called_once_with()
        self.connection.rollback.assert_not_called()
        self.assert_closed()
        self.assertEqual([call.kwargs["Key"] for call in self.s3.put_object.call_args_list],
                         ["raw/notice.pdf", "analysis/notice.pdf.json"])
        self.assertEqual(json.loads(self.s3.put_object.call_args_list[1].kwargs["Body"]), NOTICE)
        self.assertEqual([call.args[0] for call in self.embeddings.embed_query.call_args_list],
                         chunk_text(self.extract.return_value))
        for call, chunk in zip(self.cursor.execute.call_args_list, chunk_text(self.extract.return_value)):
            sql, params = call.args
            self.assertEqual(sql, "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s, %s)")
            self.assertEqual(params[:2], (chunk, [0.1, 0.2]))
            self.assertEqual(json.loads(params[2]), {"source": "notice.pdf", "type": "pdf"})

    def test_missing_db_retains_summary_and_does_not_claim_index_success(self):
        self.connect.return_value = None
        result = self.ingest()
        self.assertTrue(result.raw_saved and result.summary_saved)
        self.assertFalse(result.indexed)
        self.assertEqual(result.indexed_chunks, 0)
        self.assertEqual((result.failed_stage, result.error_code), ("index", "db_unavailable"))
        self.factory.assert_not_called()
        self.s3.delete_object.assert_not_called()

    def test_raw_upload_failure_blocks_all_downstream_calls(self):
        self.s3.put_object.side_effect = RuntimeError("offline failure")
        result = self.ingest()
        self.assertEqual(result.failed_stage, "raw_upload")
        self.assertFalse(result.raw_saved or result.summary_saved or result.indexed)
        self.extract.assert_not_called()
        self.analyze.assert_not_called()
        self.connect.assert_not_called()
        self.factory.assert_not_called()

    def test_summary_upload_failure_blocks_db_and_retains_raw(self):
        self.s3.put_object.side_effect = [None, RuntimeError("offline failure")]
        result = self.ingest()
        self.assertEqual(result.failed_stage, "summary")
        self.assertTrue(result.raw_saved)
        self.assertFalse(result.summary_saved or result.indexed)
        self.connect.assert_not_called()
        self.factory.assert_not_called()
        self.s3.delete_object.assert_not_called()

    def test_invalid_model_json_blocks_summary_storage_and_db(self):
        for invalid in ("bad json", "null", "[]", '{"title":"x","summary":"y","details":[]}'):
            with self.subTest(invalid=invalid):
                self.s3.reset_mock()
                self.analyze.return_value = invalid
                result = self.ingest()
                self.assertEqual(result.error_code, "invalid_notice")
                self.assertTrue(result.raw_saved)
                self.assertFalse(result.summary_saved or result.indexed)
                self.s3.put_object.assert_called_once()
                self.connect.assert_not_called()

    def test_model_details_null_and_unknown_fields_are_validated_before_storage(self):
        self.analyze.return_value = json.dumps({**NOTICE, "details": None, "unknown": ["keep"]})
        result = self.ingest()
        self.assertTrue(result.indexed)
        stored = json.loads(self.s3.put_object.call_args_list[1].kwargs["Body"])
        self.assertEqual(stored, {**NOTICE, "unknown": ["keep"]})

    def test_empty_extracted_text_blocks_analysis_and_db(self):
        self.extract.return_value = "   "
        result = self.ingest()
        self.assertEqual((result.failed_stage, result.error_code), ("extract_text", "no_text"))
        self.assertTrue(result.raw_saved)
        self.analyze.assert_not_called()
        self.connect.assert_not_called()

    def test_embedding_insert_and_commit_failures_rollback_close_and_keep_s3(self):
        for failure in ("factory", "embedding", "insert", "commit"):
            with self.subTest(failure=failure):
                self.reset_dependencies()
                target = {"factory": self.factory, "embedding": self.embeddings.embed_query,
                          "insert": self.cursor.execute, "commit": self.connection.commit}[failure]
                target.side_effect = RuntimeError("offline failure")
                result = self.ingest()
                self.assertEqual(result.failed_stage, "index")
                self.assertTrue(result.raw_saved and result.summary_saved)
                self.assertFalse(result.indexed)
                self.assertEqual(result.indexed_chunks, 0)
                self.connection.rollback.assert_called_once_with()
                self.assert_closed()
                self.s3.delete_object.assert_not_called()
                if failure != "commit":
                    self.connection.commit.assert_not_called()

    def test_cursor_creation_failure_rolls_back_and_closes_connection(self):
        self.connection.cursor.side_effect = RuntimeError("offline failure")
        result = self.ingest()
        self.assertFalse(result.indexed)
        self.connection.rollback.assert_called_once_with()
        self.connection.close.assert_called_once_with()
        self.cursor.close.assert_not_called()

    def test_cleanup_errors_do_not_hide_failure_or_skip_connection_close(self):
        self.cursor.execute.side_effect = RuntimeError("original failure")
        self.connection.rollback.side_effect = RuntimeError("rollback failure")
        self.cursor.close.side_effect = RuntimeError("cursor close failure")
        result = self.ingest()
        self.assertFalse(result.indexed)
        self.connection.close.assert_called_once_with()

    def test_read_cursor_closes_without_commit_and_rolls_back_on_failure(self):
        with database_cursor(self.connection) as cursor:
            cursor.execute("SELECT example", ())
        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_not_called()
        self.assert_closed()
        self.connection.reset_mock()
        self.cursor.reset_mock()
        with self.assertRaises(RuntimeError):
            with database_cursor(self.connection):
                raise RuntimeError("read failed")
        self.connection.rollback.assert_called_once_with()
        self.assert_closed()

    def test_index_missing_connection_raises_before_embedding_initialization(self):
        with self.assertRaises(DatabaseUnavailableError):
            index_notice("text", "notice.png", "png", Mock(return_value=None), self.factory)
        self.factory.assert_not_called()


class TranslationAdapterTests(OfflineTest):
    def test_actual_app_translation_falls_back_without_importing_app_or_sdks(self):
        # Extract only the function; top-level dotenv/Streamlit/AWS code never runs.
        tree = ast.parse(APP.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "translate_content")
        node.decorator_list = []
        fake_genai = Mock()
        namespace = {"validate_notice": validate_notice, "json": json, "genai": fake_genai,
                     "MODEL_NAME": "models/gemini-2.5-flash",
                     "translated_notice_or_original": translated_notice_or_original}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP), "exec"), namespace)
        translate = namespace["translate_content"]
        self.assertEqual(translate(json.dumps(NOTICE), "한국어 (Korean)"), NOTICE)
        fake_genai.GenerativeModel.assert_not_called()
        for response in ("null", "[]", "invalid", '{"title":"x","summary":"y","details":null}'):
            fake_genai.GenerativeModel.return_value.generate_content.return_value.text = response
            self.assertEqual(translate(json.dumps(NOTICE), "English"), NOTICE)
        fake_genai.GenerativeModel.return_value.generate_content.side_effect = RuntimeError("offline failure")
        self.assertEqual(translate(json.dumps(NOTICE), "English"), NOTICE)
        fake_genai.GenerativeModel.side_effect = RuntimeError("model construction failed")
        self.assertEqual(translate(json.dumps(NOTICE), "English"), NOTICE)

    def test_helper_import_reads_no_environment_and_imports_no_service_sdk(self):
        actual_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in {"boto3", "google", "psycopg2", "dotenv", "streamlit", "langchain_aws"}:
                raise AssertionError("Service SDK import is forbidden in the helper")
            return actual_import(name, *args, **kwargs)

        with patch.dict(os.environ, {}, clear=True), patch.object(os, "getenv", side_effect=AssertionError("Environment read")):
            with patch.object(builtins, "__import__", side_effect=guarded_import):
                module = runpy.run_path(str(APP.with_name("notice_helpers.py")))
        self.assertEqual(module["chunk_text"]("학교"), ["학교"])

    def test_network_guard_is_active(self):
        with self.assertRaisesRegex(AssertionError, "Network is forbidden"):
            socket.create_connection(("example.invalid", 443))


if __name__ == "__main__":
    unittest.main()
