"""Capture local browser states; audit routed HTTP/WebSocket requests only."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BANNER = "SYNTHETIC INPUT · FIXTURE MODEL RESPONSES · S3 / EMBEDDINGS / DATABASE MOCKED"


def route_websocket(route, blocked):
    """Audit and close non-local attempts handled by the Playwright route."""
    if urlparse(route.url).hostname in ("127.0.0.1", "localhost"):
        route.connect_to_server()
    else:
        blocked.append(route.url)
        route.close()


def capture(url, executable=None):
    from playwright.sync_api import expect, sync_playwright

    if urlparse(url).hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Capture only a local synthetic demo")
    output = ROOT / "docs" / "demo-evidence"
    output.mkdir(parents=True, exist_ok=True)
    blocked, errors = [], []
    with sync_playwright() as playwright:
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(viewport={"width": 1440, "height": 1200},
                                      device_scale_factor=1, locale="en-US", color_scheme="dark")

        def route_request(route):
            if urlparse(route.request.url).hostname in ("127.0.0.1", "localhost"):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        context.route("**/*", route_request)
        context.route_web_socket("**/*", lambda route: route_websocket(route, blocked))
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def screenshot(name):
            # Streamlit uses an inner scrolling region. Keep the notice card and
            # state banner fully visible; the full inspection data is in JSON.
            expect(page.get_by_role("button", name="Stop", exact=True)).not_to_be_visible()
            expanded = page.get_by_test_id("stExpander").locator("details[open] > summary")
            if expanded.count():
                expanded.click()
                expect(page.get_by_test_id("stExpander").get_by_test_id("stText")).not_to_be_visible()
            page.screenshot(path=str(output / f"{name}.png"), full_page=True)

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        expect(page.get_by_text("No synthetic notice processed yet.", exact=False)).to_be_visible()
        expect(page.get_by_text(BANNER, exact=True)).to_be_visible()
        expect(page.get_by_test_id("stApp")).to_have_css("background-color", "rgb(255, 252, 247)")
        scenario_input = page.get_by_role("combobox", name="Injected scenario", exact=True)
        expect(scenario_input.locator("..")).to_have_css("background-color", "rgb(237, 245, 250)")
        expect(scenario_input).to_have_css("color", "rgb(36, 61, 75)")
        expect(page.get_by_text("Start with success.", exact=False)).to_have_css("color", "rgb(82, 108, 125)")
        page.evaluate("document.fonts.ready")
        screenshot("empty")
        page.get_by_role("button", name="Process synthetic PDF", exact=True).click()
        expect(page.get_by_text("Local replay complete:", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Download reproducible replay JSON", exact=True)).to_be_visible()
        screenshot("success")
        for scenario in ("missing_db", "invalid_json"):
            page.get_by_role("combobox").nth(0).click()
            page.get_by_role("option", name=scenario, exact=True).click()
            page.get_by_role("button", name="Process synthetic PDF", exact=True).click()
            if scenario == "missing_db":
                expect(page.get_by_text("Summary retained in memory;", exact=False)).to_be_visible()
            else:
                expect(page.get_by_text("Replay stopped at summary (invalid_notice).", exact=True)).to_be_visible()
            expect(page.get_by_text(BANNER, exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Download reproducible replay JSON", exact=True)).to_be_visible()
            screenshot(scenario)
        page.get_by_role("button", name="Reset demo", exact=True).click()
        expect(page.get_by_text("No synthetic notice processed yet.", exact=False)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 1600})
        expect(page.get_by_text(BANNER, exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Process synthetic PDF", exact=True)).to_be_visible()
        horizontal_overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        if horizontal_overflow:
            raise AssertionError("Mobile viewport has horizontal overflow")
        screenshot("mobile_empty")
        if errors:
            raise AssertionError(f"Browser JavaScript errors: {errors}")
        evidence = {"browser": browser.version, "viewport": {"width": 1440, "height": 1200},
                    "states": ["empty", "success", "missing_db", "invalid_json", "reset"],
                    "javascript_errors": errors, "blocked_external_requests": blocked,
                    "request_audit_scope": "Playwright-routed browser-context HTTP/WebSocket requests only; not OS-wide egress isolation",
                    "preferred_color_scheme": "dark",
                    "observed_light_theme": {"background": "rgb(255, 252, 247)", "select_background": "rgb(237, 245, 250)", "caption_color": "rgb(82, 108, 125)"},
                    "mobile_viewport": {"width": 390, "height": 1600, "horizontal_overflow": horizontal_overflow},
                    "mode": "actual local browser; fixture responses and services mocked",
                    "screenshot_view": "inspection panel collapsed; complete trace in replay JSON"}
        (output / "browser.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        browser.close()
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8512")
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    capture(args.url, args.browser_executable)
