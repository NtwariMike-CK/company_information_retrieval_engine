"""Shared helpers for the real-run scripts. These scripts only USE the app through its normal API with ordinary
user accounts. They never change the AI configuration, so they are safe to run against your real (paid) stack."""
import os, sys, time
import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000")


def env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        sys.exit(f"Missing environment variable {name}. See real_run/RUNBOOK.md, step 2.")
    return v


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=120)


def login(c: httpx.Client, email: str, password: str) -> str:
    r = c.post("/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        sys.exit(f"Login failed for {email}: {r.status_code} {r.text[:120]}")
    return r.json()["access_token"]


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def ask(c: httpx.Client, token: str, question: str) -> tuple[dict | None, float, str]:
    """Open a fresh chat, ask one question. Returns (response json or None, wall-clock seconds, error text)."""
    t = time.perf_counter()
    try:
        conv = c.post("/chat/conversations", headers=hdr(token))
        conv.raise_for_status()
        r = c.post(f"/chat/conversations/{conv.json()['id']}/messages", headers=hdr(token), json={"question": question})
        dt = time.perf_counter() - t
        if r.status_code != 200:
            return None, dt, f"HTTP {r.status_code}: {r.text[:120]}"
        return r.json(), dt, ""
    except Exception as e:  # network error, timeout
        return None, time.perf_counter() - t, repr(e)[:120]
