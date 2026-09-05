"""Real Chromium + built UI + FastAPI regression; not formal MVRG or Preview.

Uses only authored public inputs, ephemeral storage and disabled LLM providers.
Positive solves use real HTTP and the unchanged product engine. Only the named
stale-response and service-failure scenarios intercept transport, explicitly.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import urllib.request
from importlib.metadata import version

from playwright.async_api import async_playwright, expect

API = "http://127.0.0.1:8000"
UI = "http://127.0.0.1:4173"
A = "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 중력가속도 g=9.81m/s²일 때 가속도를 구하라."
B = A.replace("30도", "60도")
UNITS = A.replace("5kg", "5000g")
MISSING = "질량 5kg인 블록이 마찰 없는 경사면에서 미끄러진다. 경사면 각도는 주어지지 않았다. 가속도를 구하라."
UNSUPPORTED = "공기저항 계수가 속도에 따라 변하는 변형 가능한 막대의 3차원 충돌을 해석하라."


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wait_for_server(url: str, process: subprocess.Popen, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Local server exited: {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Local server did not become ready: {url}")


async def verify(root: Path, output: Path, report: dict) -> None:
    async with async_playwright() as tool:
        browser = await tool.chromium.launch(headless=True)
        report["browser"] = browser.version
        context = await browser.new_context(viewport={"width": 1365, "height": 1000}, accept_downloads=True)
        page = await context.new_page()
        errors: list[str] = []
        http_errors: list[dict] = []
        page.on("response", lambda res: http_errors.append({"url": res.url, "status": res.status})
                if res.url.startswith(API + "/") and res.status >= 400 else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(20_000)
        solve_requests: list[dict] = []
        page.on("request", lambda req: solve_requests.append(req.post_data_json)
                if req.url == f"{API}/solve" and req.method == "POST" else None)

        async def solve(text: str, name: str) -> dict:
            await page.locator("#problem-input").fill(text)
            await expect(page.locator(".answer-block")).to_have_count(0)
            async with page.expect_response(lambda res: res.url == f"{API}/solve" and res.request.method == "POST") as pending:
                await page.get_by_role("button", name="문제 풀기", exact=True).click()
            response = await pending.value
            data = await response.json()
            write_json(output / f"{name}.json", {"input": text, "request": response.request.post_data_json,
                       "http_status": response.status, "response": data})
            assert response.status == 200, (name, response.status, data)
            assert response.request.post_data_json["problem_text"] == text
            await expect(page.get_by_role("button", name="문제 풀기", exact=True)).to_be_enabled()
            await expect(page.locator("#problem-input")).to_have_value(text)
            await expect(page.locator(".answer-block")).to_have_count(1)
            return data

        def check_incline(data: dict, degrees: int) -> None:
            assert data["ok"] is True and data["verification"]["passed"] is True, data.get("unsupported_reason")
            assert data["diagnosis"]["selected_solver"] == "incline_no_friction"
            knowns = data["diagnosis"]["canonical"]["knowns"]
            assert knowns["theta"]["value"] == degrees
            assert knowns["m"]["value"] == 5 and knowns["m"]["unit"] == "kg"
            assert math.isclose(knowns["g"]["value"], 9.81, abs_tol=1e-12)
            # Independent elementary oracle; never supplied to the product.
            assert math.isclose(data["answer"]["numeric"], 9.81 * math.sin(math.radians(degrees)), abs_tol=0.0000051)
            assert data["answer"]["unit"] == "m/s²"
            assert data["steps"] and data["verification"]["checks"]

        try:
            await page.goto(UI, wait_until="networkidle")
            await expect(page.locator("#problem-input")).to_be_visible()
            assert len(await page.locator("body").inner_text()) > 100
            assert await page.locator("[data-nextjs-dialog], .vite-error-overlay").count() == 0
            status = await (await context.request.get(f"{API}/explain/status")).json()
            assert status["enabled"] is False
            report["provider_status"] = status
            report["checks"]["page_and_disabled_provider"] = "PASS"

            a = await solve(A, "normal-30deg")
            check_incline(a, 30)
            await expect(page.locator(".ans-val").first).to_contain_text("4.905")
            await page.screenshot(path=str(output / "normal-solve.png"), full_page=True)
            report["checks"]["natural_language_to_verified_answer"] = "PASS"

            async with page.expect_response(lambda res: res.url == f"{API}/records" and res.request.method == "POST") as pending:
                await page.get_by_role("button", name="오답노트 저장", exact=True).click()
            saved_response = await pending.value
            saved = await saved_response.json()
            assert saved_response.status == 200 and saved["verified"] is True
            assert saved["problem_text"] == A
            assert saved_response.request.post_data_json["raw_result"] == a
            # RecordItem intentionally omits raw_result. Read back the persisted
            # artifact through the existing full-fidelity export API instead.
            export_response = await context.request.get(f"{API}/records/export")
            assert export_response.status == 200
            persisted = next(item for item in (await export_response.json())["records"] if item["id"] == saved["id"])
            assert persisted["problem_text"] == A and persisted["raw_result"] == a
            write_json(output / "saved-result.json", persisted)
            report["checks"]["saved_input_receipt_result_identity"] = "PASS"

            b = await solve(B, "changed-60deg")
            check_incline(b, 60)
            assert a["answer"]["numeric"] != b["answer"]["numeric"]
            report["checks"]["changed_condition_recalculated"] = "PASS"
            units = await solve(UNITS, "changed-units")
            check_incline(units, 30)
            report["checks"]["grams_to_kilograms"] = "PASS"

            await page.reload(wait_until="networkidle")
            await page.get_by_role("button", name="오답노트", exact=True).click()
            await expect(page.locator(".rec").filter(has_text=A)).to_have_count(1)
            await expect(page.locator(".rec").filter(has_text=A).locator(".rec-ans")).to_contain_text("4.905")
            async with page.expect_download() as download:
                await page.get_by_role("button", name="오답노트 백업 JSON 내려받기", exact=True).click()
            exported_path = output / "notebook-export.json"
            await (await download.value).save_as(str(exported_path))
            exported = json.loads(exported_path.read_text(encoding="utf-8"))
            assert exported["server_available"] is True
            assert any(item["id"] == saved["id"] and item["problem_text"] == A and item["raw_result"] == a for item in exported["records"])
            report["checks"]["reload_history_and_actual_export"] = "PASS"
            async with page.expect_response(lambda res: res.url == f"{API}/solve" and res.request.method == "POST") as pending:
                await page.locator(".rec").filter(has_text=A).get_by_role("button", name="다시 풀기", exact=True).click()
            reopened = await (await pending.value).json()
            check_incline(reopened, 30)
            await expect(page.locator("#problem-input")).to_have_value(A)
            report["checks"]["history_rerun"] = "PASS"

            for text, name in ((MISSING, "missing-angle"), (UNSUPPORTED, "unsupported")):
                data = await solve(text, name)
                assert not (data.get("ok") and data.get("verification", {}).get("passed")), name
                await expect(page.locator(".answer-block .ans-val")).to_have_count(0)
                await expect(page.get_by_role("button", name="오답노트 저장", exact=True)).to_have_count(0)
                report["checks"][name] = "PASS"

            # Only delay an actual server response; its bytes are not fabricated.
            async def delayed_response(route):
                real_response = await route.fetch()
                await page.locator("#problem-input").fill(B)
                await route.fulfill(response=real_response)

            await page.route(f"{API}/solve", delayed_response, times=1)
            await page.locator("#problem-input").fill(A)
            async with page.expect_response(lambda res: res.url == f"{API}/solve" and res.request.method == "POST") as pending:
                await page.get_by_role("button", name="문제 풀기", exact=True).click()
            late = await (await pending.value).json()
            check_incline(late, 30)
            await expect(page.locator("#problem-input")).to_have_value(B)
            await expect(page.locator(".answer-block")).to_have_count(0)
            await expect(page.get_by_role("button", name="문제 풀기", exact=True)).to_be_enabled()
            report["checks"]["late_real_response_after_edit"] = "PASS"

            before = len(solve_requests)
            async with page.expect_response(lambda res: res.url == f"{API}/solve" and res.request.method == "POST") as pending:
                await page.evaluate("""() => { const b = [...document.querySelectorAll('button')].find(node => node.textContent.trim() === '문제 풀기'); if (!b) throw new Error('solve button missing'); b.click(); b.click(); }""")
            duplicate = await (await pending.value).json()
            check_incline(duplicate, 60)
            await expect(page.locator(".answer-block .ans-val")).to_have_count(1)
            assert len(solve_requests) == before + 1
            report["checks"]["same_tick_duplicate_click"] = "PASS"

            # An explicitly injected 503 tests error UI, never positive solver evidence.
            await page.route(f"{API}/solve", lambda route: route.fulfill(status=503, json={"detail": "closure-injected-service-failure"}), times=1)
            await page.get_by_role("button", name="문제 풀기", exact=True).click()
            await expect(page.locator(".notice.err")).to_contain_text("closure-injected-service-failure")
            await expect(page.locator(".answer-block")).to_have_count(0)
            await expect(page.get_by_role("button", name="문제 풀기", exact=True)).to_be_enabled()
            report["checks"]["injected_503_no_stale_success"] = "PASS"
            # The Generic UI is a separate interpretation/provider entrypoint.
            # With credentials/config deliberately disabled, exercise its real
            # fail-closed path without calling that an end-to-end Gen2 success.
            generic_url = f"{API}/api/mechanics/multimodal/evidence"
            async with page.expect_response(lambda res: res.url == generic_url and res.request.method == "POST") as pending:
                await page.get_by_role("button", name="Generic 경로로 분석하고 풀기", exact=True).click()
            generic_response = await pending.value
            generic_body = await generic_response.json()
            assert generic_response.status == 503
            assert generic_body["detail"]["code"] in {"multimodal_modeler_unavailable", "multimodal_revision_store_unavailable"}
            await expect(page.locator(".mechanics-multimodal-panel [role='alert']")).to_be_visible()
            await expect(page.locator(".mechanics-verified-result")).to_have_count(0)
            await expect(page.get_by_role("button", name="Generic 경로로 분석하고 풀기", exact=True)).to_be_enabled()
            report["generic_natural_language_pipeline"] = {"status": "BLOCKED_EXTERNAL", "reason": generic_body["detail"]["code"]}
            write_json(output / "generic-unconfigured.json", generic_body)
            report["checks"]["generic_unconfigured_environment_fails_closed"] = "PASS"
            assert http_errors == [{"url": f"{API}/solve", "status": 503}, {"url": generic_url, "status": 503}], http_errors
            report["checks"]["no_unexpected_api_errors_including_cold_start"] = "PASS"
            assert not errors, errors
            report["checks"]["no_uncaught_browser_errors"] = "PASS"
            report["status"] = "PASS"
        finally:
            report["browser_errors"] = errors
            report["http_errors"] = http_errors
            report["observed_solve_requests"] = solve_requests
            await page.screenshot(path=str(output / "final-screen.png"), full_page=True)
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert head == args.head_sha
    report = {"status": "FAIL", "code_head": head, "scope": "authored-product-browser-regression",
              "formal_mvrg": "NOT_RUN", "preview_deployment": "NOT_RUN", "checks": {},
              "python": platform.python_version(), "playwright": version("playwright"),
              "runtime_versions": {p: version(p) for p in ("fastapi", "pydantic", "sympy", "pint", "numpy", "scipy")},
              "built_app_sha256": hashlib.sha256((root / "frontend/out/assets/app.js").read_bytes()).hexdigest()}
    environment = dict(os.environ)
    environment.update({"DYNATUTOR_ENV": "development", "RENDER": "false", "LLM_ENABLED": "false",
                        "MECHANICS_MULTIMODAL_PROVIDER": "disabled", "MECHANICS_MODELER_ENABLED": "false",
                        "DYNATUTOR_ACCESS_TOKEN": "", "DYNATUTOR_DB": str(output / "isolated-records.sqlite"),
                        "DYNATUTOR_CORS_ORIGINS": UI, "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "",
                        "OPENAI_BASE_URL": "", "ANTHROPIC_BASE_URL": "", "MECHANICS_MODELER_BASE_URL": "",
                        "MECHANICS_FIGURE_BASE_URL": ""})
    processes = []
    try:
        with (output / "backend.log").open("w") as backend_log, (output / "frontend.log").open("w") as frontend_log:
            backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=root / "backend", env=environment, stdout=backend_log, stderr=subprocess.STDOUT)
            processes.append(backend)
            frontend = subprocess.Popen([sys.executable, "-m", "http.server", "4173", "--bind", "127.0.0.1", "--directory", str(root / "frontend/out")], stdout=frontend_log, stderr=subprocess.STDOUT)
            processes.append(frontend)
            wait_for_server(API, backend)
            wait_for_server(UI, frontend)
            asyncio.run(verify(root, output, report))
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        write_json(output / "browser-report.json", report)
        print(json.dumps({"status": report["status"], "head": head, "checks": report["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
