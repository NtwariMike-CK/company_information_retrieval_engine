"""Browser end-to-end test + screenshots + front-end performance profiles (Playwright / Chromium).
Needs: API on :8000, front-end on :3000 (production build), `pip install playwright` + `playwright install chromium`.
WARNING: switches the GLOBAL AI config to the test providers and creates a demo company - throwaway stack only.
    python tests/e2e_browser.py <output_dir>          (screenshots + e2e_results.json go to <output_dir>)
Engines: only Chromium is automated here. Device rows are Chromium EMULATION (viewport, touch, user agent, CPU/network throttling);
Safari/Firefox and physical devices must be tested by hand - see docs/testing."""
import json, os, statistics, sys, time, uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

API = os.getenv("BASE_URL", "http://localhost:8000")
WEB = os.getenv("WEB_URL", "http://localhost:3000")
SA = (os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com"), os.getenv("SUPERADMIN_PASSWORD", "ChangeMe123!"))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e_out"); OUT.mkdir(parents=True, exist_ok=True)
DEMO = Path(__file__).resolve().parents[2] / "demo" / "documents"
run = uuid.uuid4().hex[:6]
results = {"checks": [], "shots": [], "perf": {}, "errors": []}


def check(name, cond, extra=""):
    results["checks"].append({"name": name, "pass": bool(cond), "detail": extra})
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if not cond and extra else ""))


# ------------------------------------------------------------------ seed data through the API
api = httpx.Client(base_url=API, timeout=90)
tok = api.post("/auth/login", json={"email": SA[0], "password": SA[1]}).json()["access_token"]
sh = {"Authorization": f"Bearer {tok}"}
api.put("/superadmin/rag-config", headers=sh, json={"embedding_cfg": {"provider": "fake", "model": "gemini-embedding-2"}, "llm_cfg": {"provider": "fake"},
        "retrieval_cfg": {"min_score": 0.25, "final_k": 4}, "chunking_cfg": {"strategy": "parent_child", "parent_size": 800, "child_size": 250, "overlap": 30}})
ADMIN, EMP, PW = f"admin-{run}@acmerwanda.com", f"employee-{run}@acmerwanda.com", "Password123"
co = api.post("/superadmin/companies", headers=sh, json={"company_name": f"Acme Rwanda Ltd {run}", "admin_name": "Aline Uwase", "phone": "+250788123456", "email": ADMIN, "password": PW})
ah = {"Authorization": "Bearer " + api.post("/auth/login", json={"email": ADMIN, "password": PW}).json()["access_token"]}
api.post("/company/employees", headers=ah, json={"full_name": "Eric Mugisha", "email": EMP, "password": PW})
files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in sorted(DEMO.iterdir())]
api.post("/company/documents", headers=ah, files=files)
for _ in range(90):
    docs = api.get("/company/documents", headers=ah).json()
    if docs and all(d["status"] in ("ready", "failed") for d in docs):
        break
    time.sleep(1)
check("seed: demo documents (PDF, DOCX, Kinyarwanda MD) processed to ready", len(docs) == 3 and all(d["status"] == "ready" for d in docs), str([(d["filename"], d["status"]) for d in docs]))
check("seed: service started", api.post("/company/service/start", headers=ah).status_code == 200)
eh = {"Authorization": "Bearer " + api.post("/auth/login", json={"email": EMP, "password": PW}).json()["access_token"]}
for qn in ["What is the remote work policy?", "How many days of annual leave do employees get?", "What is the remote work policy?"]:   # populate analytics
    cv = api.post("/chat/conversations", headers=eh).json()["id"]; api.post(f"/chat/conversations/{cv}/messages", headers=eh, json={"question": qn})


def shot(page, name, full=False):
    try:
        page.wait_for_timeout(500); page.screenshot(path=str(OUT / f"{name}.png"), full_page=full); results["shots"].append(name)
    except Exception as e:
        results["errors"].append(f"screenshot {name}: {e}")


def login(page, email, pw):
    page.goto(f"{WEB}/login"); page.fill('input[type="email"]', email); page.fill('input[type="password"]', pw)
    page.click('button:has-text("Sign in")'); page.wait_for_load_state("networkidle")


def ask(page, text):
    page.fill("textarea", text)
    t = time.perf_counter()
    with page.expect_response(lambda r: "/messages" in r.url and r.request.method == "POST", timeout=60000) as ri:
        page.click('button[aria-label="Send"]')
    resp = ri.value
    page.wait_for_load_state("networkidle")
    return resp.status, (time.perf_counter() - t) * 1000


with sync_playwright() as pw:
    chromium = pw.chromium.launch()
    results["browser"] = {"engine": "Chromium", "version": chromium.version}
    ctx = chromium.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    msgs = []
    page.on("console", lambda m: msgs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: msgs.append(str(e)))

    # ---- public site
    page.goto(WEB); page.wait_for_load_state("networkidle")
    check("landing page renders hero from the database", "knowledge" in page.inner_text("body").lower())
    shot(page, "01_landing_desktop", full=True)
    page.goto(f"{WEB}/login"); shot(page, "02_login")
    page.fill('input[type="email"]', ADMIN); page.fill('input[type="password"]', "wrong-password"); page.click('button:has-text("Sign in")'); page.wait_for_timeout(1200)
    check("wrong password shows a safe error message, stays on /login", "/login" in page.url and "invalid" in page.inner_text("body").lower())
    shot(page, "03_login_error")
    page.goto(f"{WEB}/chat"); page.wait_for_load_state("networkidle")
    check("protected page without a session redirects to /login", "/login" in page.url)
    for ico in ("/icon.svg", "/favicon.ico", "/apple-icon.png"):
        check(f"favicon asset {ico} is served", httpx.get(WEB + ico).status_code == 200)

    # ---- employee
    login(page, EMP, PW)
    check("employee lands on the chat page", "/chat" in page.url)
    shot(page, "04_employee_chat_empty")
    status, ms = ask(page, "How many days of annual leave do employees get?")
    check("English question answered through the UI", status == 200, f"HTTP {status}")
    results["perf"]["chat_answer_ui_ms_en"] = round(ms)
    shot(page, "05_employee_chat_answer_en")
    status, ms = ask(page, "Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?")
    check("Kinyarwanda question answered through the UI", status == 200, f"HTTP {status}")
    shot(page, "06_employee_chat_answer_rw")
    page.click('button:has-text("Report")'); page.wait_for_timeout(400); shot(page, "07_employee_report_form")
    page.goto(f"{WEB}/admin"); page.wait_for_load_state("networkidle")
    check("employee is kept out of the admin area", "/admin" not in page.url or "forbidden" in page.inner_text("body").lower() or "/chat" in page.url or "/login" in page.url, page.url)
    ctx.close()

    # ---- company admin
    ctx = chromium.new_context(viewport={"width": 1440, "height": 900}); page = ctx.new_page(); page.on("pageerror", lambda e: msgs.append(str(e)))
    login(page, ADMIN, PW)
    check("company admin lands in the admin area", "/admin" in page.url)
    shot(page, "08_admin_dashboard")
    for path, name in (("/admin/documents", "09_admin_documents"), ("/admin/employees", "10_admin_employees"), ("/admin/analytics", "11_admin_analytics")):
        page.goto(WEB + path); page.wait_for_load_state("networkidle"); check(f"admin page {path} renders", page.locator("main, body").first.inner_text().strip() != "")
        shot(page, name)
    page.goto(f"{WEB}/superadmin"); page.wait_for_load_state("networkidle")
    check("company admin cannot open the SuperAdmin area", "/superadmin" not in page.url or "forbidden" in page.inner_text("body").lower() or "/admin" in page.url, page.url)
    ctx.close()

    # ---- superadmin
    ctx = chromium.new_context(viewport={"width": 1440, "height": 900}); page = ctx.new_page(); page.on("pageerror", lambda e: msgs.append(str(e)))
    login(page, SA[0], SA[1])
    check("superadmin lands in the SuperAdmin area", "/superadmin" in page.url)
    for path, name in (("/superadmin", "12_superadmin_companies"), ("/superadmin/applications", "13_superadmin_applications"), ("/superadmin/rag", "14_superadmin_rag_settings"),
                       ("/superadmin/model-eval", "15_superadmin_model_evaluation"), ("/superadmin/content", "16_superadmin_content"),
                       ("/superadmin/analytics", "17_superadmin_analytics"), ("/superadmin/evaluation", "18_superadmin_feedback_settings")):
        page.goto(WEB + path); page.wait_for_load_state("networkidle"); check(f"superadmin page {path} renders without error", "application error" not in page.inner_text("body").lower())
        shot(page, name, full=(path == "/superadmin/rag"))
    page.goto(f"{WEB}/superadmin/model-eval"); page.wait_for_load_state("networkidle")
    try:
        page.locator("text=/retrieval/i").first.click(timeout=3000); page.wait_for_timeout(800); shot(page, "19_model_evaluation_run_detail", full=True)
    except Exception as e:
        results["errors"].append(f"run detail: {e}")
    ctx.close()

    # ---- responsive / device emulation (Chromium emulation, not real hardware)
    for dev, name in (("iPhone 13", "20_chat_iphone13_emulated"), ("Pixel 7", "21_chat_pixel7_emulated"), ("iPad (gen 7)", "22_chat_ipad_emulated")):
        ctx = chromium.new_context(**pw.devices[dev]); page = ctx.new_page(); login(page, EMP, PW)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check(f"{dev} (emulated): chat page has no horizontal scroll", not overflow)
        shot(page, name); ctx.close()
    ctx = chromium.new_context(**pw.devices["iPhone 13"]); page = ctx.new_page(); page.goto(WEB); page.wait_for_load_state("networkidle"); shot(page, "23_landing_iphone13_emulated"); ctx.close()

    # ---- performance profiles: load time per page under throttling (3 runs, median)
    PROFILES = {"Desktop, no throttling": (1, None), "Mid-range phone (4x CPU slowdown, 4G 9 Mbps / 170 ms)": (4, (9e6 / 8, 9e6 / 8, 170)),
                "Low-end phone (6x CPU slowdown, slow 3G 400 kbps / 400 ms)": (6, (400e3 / 8, 400e3 / 8, 400))}
    LCP = "new Promise(r=>{let v=0;new PerformanceObserver(l=>{for(const e of l.getEntries())v=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});setTimeout(()=>r(v),800)})"
    for pname, (cpu, net) in PROFILES.items():
        rows = {}
        for label, path, who in (("Landing page", "/", None), ("Login page", "/login", None), ("Chat (signed in)", "/chat", EMP), ("Model evaluation (SuperAdmin)", "/superadmin/model-eval", SA[0])):
            loads, lcps = [], []
            for _ in range(3):
                ctx = chromium.new_context(viewport={"width": 1280, "height": 800}); page = ctx.new_page()
                if who:
                    login(page, who, PW if who == EMP else SA[1])
                cdp = ctx.new_cdp_session(page); cdp.send("Emulation.setCPUThrottlingRate", {"rate": cpu})
                cdp.send("Network.enable"); cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})   # cold load even after sign-in
                if net:
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "downloadThroughput": net[0], "uploadThroughput": net[1], "latency": net[2]})
                t = time.perf_counter(); page.goto(WEB + path, wait_until="load"); loads.append((time.perf_counter() - t) * 1000)
                lcps.append(page.evaluate(LCP)); ctx.close()
            rows[label] = {"load_ms_median": round(statistics.median(loads)), "lcp_ms_median": round(statistics.median(lcps))}
        results["perf"][pname] = rows
        print(pname, json.dumps(rows))
    chromium.close()

results["console_errors"] = sorted(set(msgs))[:10]
check("no uncaught JavaScript errors during the whole run", not [m for m in msgs if "pageerror" in m or "Uncaught" in m or "TypeError" in m], str(msgs[:3]))
passed = sum(c["pass"] for c in results["checks"])
results["summary"] = {"passed": passed, "total": len(results["checks"]), "screenshots": len(results["shots"])}
(OUT / "e2e_results.json").write_text(json.dumps(results, indent=1))
print(f"\n{passed} of {len(results['checks'])} browser checks passed; {len(results['shots'])} screenshots; errors: {results['errors']}")
sys.exit(0 if passed == len(results["checks"]) else 1)
