"""
Frontend sanity test — verifies the Next.js dev server is up and the API
proxy to the backend works correctly.

Usage (both servers must be running):
    python tests/sanity_frontend.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""
import json
import sys
import urllib.error
import urllib.request

FRONTEND = "http://localhost:3000"
BACKEND = "http://localhost:8000"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


# ── helpers ──────────────────────────────────────────────────────────────────

def raw_get(url: str, timeout: int = 10) -> tuple[int, bytes, dict]:
    """Returns (status_code, body_bytes, headers_dict)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def check(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    line = f"  [{tag}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    results.append((name, ok, detail))


# ── test cases ────────────────────────────────────────────────────────────────

def test_frontend_reachable():
    status, body, headers = raw_get(FRONTEND)
    ok = status == 200
    ct = headers.get("Content-Type", "")
    check("Frontend reachable (GET /)", ok, f"status={status} content-type={ct[:30]}")


def test_frontend_returns_html():
    status, body, _ = raw_get(FRONTEND)
    ok = status == 200 and b"<html" in body.lower()
    check("Frontend returns HTML", ok, f"html_tag_found={b'<html' in body.lower()}")


def test_frontend_has_expected_meta():
    status, body, _ = raw_get(FRONTEND)
    # Next.js always injects __NEXT_DATA__ or similar markers
    has_next = b"__NEXT" in body or b"_next" in body
    check("Frontend has Next.js markers", has_next, f"has_next_marker={has_next}")


def test_proxy_health():
    """The Next.js rewrite should forward /health → backend."""
    status, body, _ = raw_get(f"{FRONTEND}/health")
    try:
        data = json.loads(body)
        ok = status == 200 and "status" in data
        detail = f"proxy_status={data.get('status','—')}"
    except Exception:
        ok = False
        detail = f"status={status} body={body[:60]!r}"
    check("Proxy /health → backend", ok, detail)


def test_proxy_api_sessions():
    """The rewrite should forward /api/chat/sessions → backend."""
    status, body, _ = raw_get(f"{FRONTEND}/api/chat/sessions")
    try:
        data = json.loads(body)
        ok = status == 200 and "sessions" in data
        detail = f"sessions_count={len(data.get('sessions', []))}"
    except Exception:
        ok = False
        detail = f"status={status} body={body[:80]!r}"
    check("Proxy /api/chat/sessions → backend", ok, detail)


def test_proxy_research_sessions():
    """The rewrite should forward /api/research/sessions → backend."""
    status, body, _ = raw_get(f"{FRONTEND}/api/research/sessions")
    try:
        data = json.loads(body)
        ok = status == 200 and "sessions" in data
        detail = f"sessions_count={len(data.get('sessions', []))}"
    except Exception:
        ok = False
        detail = f"status={status} body={body[:80]!r}"
    check("Proxy /api/research/sessions → backend", ok, detail)


def test_static_assets():
    """/_next/static/ should serve JS/CSS chunks."""
    # Fetch the root page first to find a real chunk URL
    _, body, _ = raw_get(FRONTEND)
    import re
    # Next.js embeds chunk paths like /_next/static/chunks/...
    match = re.search(rb'/_next/static/[^\s"\']+\.js', body)
    if not match:
        check("Static JS assets reachable", False, "could not find /_next/static chunk URL in HTML")
        return
    chunk_url = f"{FRONTEND}{match.group(0).decode()}"
    status, chunk_body, headers = raw_get(chunk_url)
    ct = headers.get("Content-Type", "")
    ok = status == 200 and ("javascript" in ct or len(chunk_body) > 100)
    check("Static JS assets reachable", ok, f"status={status} url=...{chunk_url[-40:]}")


def test_backend_directly_reachable():
    """Sanity: the backend itself is up (independent of the proxy)."""
    status, body, _ = raw_get(f"{BACKEND}/health")
    try:
        data = json.loads(body)
        ok = status == 200
        detail = f"backend_status={data.get('status','—')}"
    except Exception:
        ok = False
        detail = f"status={status}"
    check("Backend directly reachable", ok, detail)


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    print(f"\nResearch Agent — Frontend Sanity Tests")
    print(f"Frontend: {FRONTEND}")
    print(f"Backend:  {BACKEND}\n")

    test_backend_directly_reachable()
    test_frontend_reachable()
    test_frontend_returns_html()
    test_frontend_has_expected_meta()
    test_proxy_health()
    test_proxy_api_sessions()
    test_proxy_research_sessions()
    test_static_assets()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'─' * 44}")
    print(f"  Result: {passed}/{total} checks passed")
    if passed < total:
        print(f"\n  Failed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"    • {name}" + (f" ({detail})" if detail else ""))
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
