"""
Backend sanity test — runs against a live server at http://localhost:8000.

Usage (venv must be active, server must be running):
    python tests/sanity_backend.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


# ── helpers ──────────────────────────────────────────────────────────────────

def get(path: str, timeout: int = 10) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"_error": str(e)}


def post(path: str, body: dict | None = None, timeout: int = 15) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"_error": str(e)}


def delete(path: str, timeout: int = 10) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()) if e.read() else {}
    except Exception as e:
        return 0, {"_error": str(e)}


def check(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    line = f"  [{tag}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    results.append((name, ok, detail))


# ── test cases ────────────────────────────────────────────────────────────────

def test_server_reachable():
    status, body = get("/")
    check("Server reachable (GET /)", status == 200, f"status={status}")


def test_health():
    status, body = get("/health")
    ok = status == 200 and body.get("status") in ("healthy", "degraded")
    check("Health endpoint (GET /health)", ok, body.get("status", "no status"))


def test_ollama_connected():
    status, body = get("/health")
    ollama_status = (body.get("services") or {}).get("ollama", "unknown")
    check("Ollama connected", ollama_status == "available", f"ollama={ollama_status}")


def test_llm_endpoint():
    status, body = get("/api/research/test/llm", timeout=30)
    ok = status == 200 and body.get("success") is True
    check("LLM test (GET /api/research/test/llm)", ok, body.get("response", body.get("_error", "")))


def test_chat_session_lifecycle():
    # Create
    status, body = post("/api/chat/sessions", {"title": "Sanity test", "mode": "chat"})
    ok_create = status == 200 and "id" in body
    check("Create chat session", ok_create, f"status={status}")
    if not ok_create:
        return

    session_id = body["id"]

    # List
    status, body = get("/api/chat/sessions")
    ids = [s["id"] for s in (body.get("sessions") or [])]
    check("List sessions contains new session", session_id in ids, f"found={session_id in ids}")

    # Get
    status, body = get(f"/api/chat/sessions/{session_id}")
    check("Get session by id", status == 200 and body.get("id") == session_id)

    # Rename
    req = urllib.request.Request(
        f"{BASE}/api/chat/sessions/{session_id}/rename",
        data=json.dumps({"title": "Renamed"}).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            rename_ok = r.status == 200
    except urllib.error.HTTPError as e:
        rename_ok = e.code == 200
    except Exception:
        rename_ok = False
    check("Rename session", rename_ok)

    # Delete
    status, _ = delete(f"/api/chat/sessions/{session_id}")
    check("Delete session", status == 200, f"status={status}")

    # Confirm gone
    status, _ = get(f"/api/chat/sessions/{session_id}")
    check("Session gone after delete", status == 404, f"status={status}")


def test_research_sessions_list():
    status, body = get("/api/research/sessions")
    ok = status == 200 and "sessions" in body
    check("Research sessions list", ok, f"status={status}")


def test_web_search():
    status, body = post("/api/research/test/search?query=python+programming&max_results=2", timeout=20)
    ok = status == 200 and isinstance(body.get("results"), list)
    check(
        "Web search test",
        ok,
        f"results={len(body.get('results', []))} status={status}",
    )


def test_academic_search():
    status, body = post("/api/research/test/academic?query=transformers&max_results=2", timeout=20)
    ok = status == 200 and isinstance(body.get("results"), list)
    check(
        "Academic search test",
        ok,
        f"results={len(body.get('results', []))} status={status}",
    )


def test_research_start_and_status():
    status, body = post(
        "/api/research/start",
        {"topic": "sanity check test topic", "max_sources": 2, "include_academic": False},
        timeout=15,
    )
    ok_start = status == 200 and "research_id" in body
    check("Research start", ok_start, f"status={status} id={body.get('research_id','—')}")
    if not ok_start:
        return

    research_id = body["research_id"]

    # Poll status up to 5s (pipeline is async — just verify the endpoint responds)
    for _ in range(3):
        time.sleep(1)
        s_status, s_body = get(f"/api/research/status/{research_id}")
        if s_status == 200:
            break

    check(
        "Research status endpoint",
        s_status == 200 and "status" in s_body,
        f"pipeline_status={s_body.get('status','—')}",
    )

    # Cleanup
    delete(f"/api/research/session/{research_id}")


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    print(f"\nResearch Agent — Backend Sanity Tests")
    print(f"Target: {BASE}\n")

    test_server_reachable()
    test_health()
    test_ollama_connected()
    test_llm_endpoint()
    test_chat_session_lifecycle()
    test_research_sessions_list()
    test_web_search()
    test_academic_search()
    test_research_start_and_status()

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
