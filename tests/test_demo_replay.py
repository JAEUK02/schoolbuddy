"""Synthetic replay tests with selected Python TCP connection calls patched."""

import ast
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from demo_replay import PDF_PATH, ROOT, SCENARIOS, fixture_responses, run_demo
from notice_helpers import chunk_text, translated_notice_or_original
from notice_inputs import extract_pdf_text
from tools.capture_demo import route_websocket


class OfflineDemoTest(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex"):
            guard = patch(target, side_effect=AssertionError("Python TCP connection forbidden in component tests"))
            guard.start()
            self.addCleanup(guard.stop)


class ReplayTests(OfflineDemoTest):
    def test_real_pdf_is_read_and_original_window_contents_are_inserted(self):
        snapshot = run_demo()
        self.assertIn("available_real_components", snapshot)
        self.assertNotIn("real_components", snapshot)
        text = snapshot["extracted_text"]
        self.assertIn("SYNTHETIC SCHOOL NOTICE", text)
        self.assertIn("2026-10-08", text)
        self.assertIn("Bring a notebook", text)
        self.assertEqual(len(text), 1486)
        self.assertEqual(snapshot["fixture_sha256"], hashlib.sha256(PDF_PATH.read_bytes()).hexdigest())
        self.assertEqual([row["content"] for row in snapshot["committed_stub_rows"]], chunk_text(text))
        self.assertEqual(snapshot["result"], dict(raw_saved=True, summary_saved=True,
                         indexed=True, indexed_chunks=2, failed_stage=None, error_code=None))
        operations = [item["operation"] for item in snapshot["trace"]]
        self.assertEqual(operations[-3:], ["database.stub.commit", "database.stub.cursor.close",
                                         "database.stub.connection.close"])
        self.assertEqual(snapshot["notice"]["fixture_id"], "synthetic-reading-club-v1")

    def test_partial_states_and_failure_order_are_visible(self):
        cases = {
            "raw_save_failure": (False, False, "raw_upload", "operation_failed"),
            "summary_save_failure": (True, False, "summary", "operation_failed"),
            "invalid_json": (True, False, "summary", "invalid_notice"),
            "empty_text": (True, False, "extract_text", "no_text"),
            "missing_db": (True, True, "index", "db_unavailable"),
            "embedding_failure": (True, True, "index", "operation_failed"),
            "commit_failure": (True, True, "index", "operation_failed"),
        }
        self.assertEqual(set(cases) | {"success"}, set(SCENARIOS))
        for scenario, (raw, summary, stage, code) in cases.items():
            with self.subTest(scenario=scenario):
                snapshot = run_demo(scenario)
                self.assertIn("available_real_components", snapshot)
                self.assertNotIn("real_components", snapshot)
                result = snapshot["result"]
                self.assertEqual(result, dict(raw_saved=raw, summary_saved=summary, indexed=False,
                                 indexed_chunks=0, failed_stage=stage, error_code=code))
                self.assertEqual(snapshot["committed_stub_rows"], [])
                self.assertEqual(snapshot["notice"] is not None, summary)
                operations = [item["operation"] for item in snapshot["trace"]]
                if not summary:
                    self.assertNotIn("database.stub.connect", operations)
                if scenario in ("embedding_failure", "commit_failure"):
                    self.assertEqual(operations[-3:], ["database.stub.rollback", "database.stub.cursor.close",
                                                     "database.stub.connection.close"])
                if scenario == "empty_text":
                    self.assertNotIn("model.fixture.reply", operations)
                if scenario == "missing_db":
                    self.assertNotIn("embedding.stub", operations)

    def test_replays_are_deterministic_and_match_committed_evidence(self):
        for scenario in ("success", "missing_db", "invalid_json"):
            with self.subTest(scenario=scenario):
                snapshot = run_demo(scenario)
                self.assertEqual(snapshot, run_demo(scenario))
                path = ROOT / "docs" / "demo-evidence" / f"{scenario}.json"
                self.assertEqual(snapshot, json.loads(path.read_text(encoding="utf-8")))

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            run_demo("unrecognized")

    def test_websocket_routing_records_blocked_attempts_and_allows_local(self):
        for url, local in (("ws://127.0.0.1:8512/stream", True),
                           ("ws://localhost:8512/stream", True),
                           ("wss://example.invalid/synthetic-audit", False)):
            with self.subTest(url=url):
                route, blocked = Mock(url=url), []
                route_websocket(route, blocked)
                if local:
                    route.connect_to_server.assert_called_once_with()
                    route.close.assert_not_called()
                    self.assertEqual(blocked, [])
                else:
                    route.connect_to_server.assert_not_called()
                    route.close.assert_called_once_with()
                    self.assertEqual(blocked, [url])

    def test_all_handwritten_languages_retain_the_analysis_shape(self):
        fixtures = fixture_responses()
        self.assertEqual(set(fixtures["translations"]), {"English", "한국어 (Korean)", "Tiếng Việt", "中文"})
        for language, response in fixtures["translations"].items():
            with self.subTest(language=language):
                self.assertEqual(translated_notice_or_original(fixtures["analysis"], response), response)
        self.assertEqual(translated_notice_or_original(fixtures["analysis"], {"title": "broken"}),
                         fixtures["analysis"])

    def test_app_pdf_seam_uses_shared_parser_and_image_routing_remains(self):
        # Execute only this existing function's AST: no live app import or SDK init.
        tree = ast.parse((ROOT / "test_jaeuk.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "extract_notice_text")
        module = ast.Module(body=[function], type_ignores=[])
        genai = Mock()
        genai.GenerativeModel.return_value.generate_content.return_value.text = "mock image reply"
        namespace = {"extract_pdf_text": extract_pdf_text, "genai": genai, "MODEL_NAME": "fixture-model"}
        exec(compile(module, "test_jaeuk.py:function-only", "exec"), namespace)
        self.assertEqual(namespace["extract_notice_text"](PDF_PATH.read_bytes(), "notice.PDF"),
                         extract_pdf_text(PDF_PATH.read_bytes()))
        genai.GenerativeModel.assert_not_called()
        for extension, mime in (("jpg", "image/jpeg"), ("png", "image/png")):
            self.assertEqual(namespace["extract_notice_text"](b"synthetic", f"notice.{extension}"), "mock image reply")
            args = genai.GenerativeModel.return_value.generate_content.call_args.args[0]
            self.assertEqual(args[1], {"mime_type": mime, "data": b"synthetic"})


class StreamlitDemoTests(OfflineDemoTest):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT / "demo_notice.py"), default_timeout=15).run()

    def test_empty_success_and_reset_ui_states(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertIn("MOCKED", app.warning[0].value)
        self.assertIn("No synthetic notice", app.info[0].value)
        app.button(key="demo_run").click().run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["Yes", "Yes", "2"])
        self.assertIn("mock commit returned", app.success[0].value)
        app.button(key="demo_reset").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        self.assertIn("No synthetic notice", app.info[0].value)

    def test_missing_database_and_invalid_json_ui_states(self):
        app = self.app()
        for scenario, expected in (("missing_db", ["Yes", "Yes", "0"]),
                                   ("invalid_json", ["Yes", "No", "0"])):
            with self.subTest(scenario=scenario):
                app.selectbox(key="demo_scenario").select(scenario).run()
                app.button(key="demo_run").click().run()
                self.assertFalse(app.exception)
                self.assertEqual([metric.value for metric in app.metric], expected)
                if scenario == "missing_db":
                    self.assertIn("indexing is incomplete", app.warning[1].value)
                else:
                    self.assertIn("invalid_notice", app.error[0].value)

    def test_four_fixture_language_cards_use_actual_shape_helper(self):
        app = self.app()
        app.button(key="demo_run").click().run()
        fixtures = fixture_responses()
        for language, response in fixtures["translations"].items():
            with self.subTest(language=language):
                app.selectbox(key="demo_language").select(language).run()
                self.assertFalse(app.exception)
                self.assertIn(response["title"], [heading.value for heading in app.subheader])


if __name__ == "__main__":
    unittest.main()
