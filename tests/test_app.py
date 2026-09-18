import pytest
from fastapi.testclient import TestClient

from happy import model, store, web
from happy.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setattr(model, "llm", None)
    with TestClient(app) as c:
        yield c


def test_dashboard_and_skills(client):
    assert client.get("/").status_code == 200
    skills = client.get("/api/skills").json()
    assert len(skills) == 100
    assert len({s["id"] for s in skills}) == 100
    assert client.get("/api/status").json()["skills"] == 100


def test_knowledge_lifecycle(client):
    r = client.post(
        "/api/knowledge", json={"title": "Orbits", "content": "Planets orbit stars"}
    )
    assert r.status_code == 200
    assert store.retrieve("planets")[0]["title"] == "Orbits"
    assert len(client.get("/api/knowledge").json()) == 1
    assert client.delete("/api/knowledge/" + str(r.json()["id"])).status_code == 200
    assert client.get("/api/knowledge").json() == []


def test_offline_chat(client):
    r = client.post("/api/chat", json={"message": "Hello"})
    assert r.status_code == 200
    assert not r.json()["generated"]
    assert "not loaded" in r.json()["answer"]
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert (
        client.post("/api/chat", json={"message": "hi", "skill": "missing"}).status_code
        == 400
    )


def test_search_and_context(client, monkeypatch):
    monkeypatch.setattr(
        web,
        "search",
        lambda q: [
            {
                "title": "Test source",
                "url": "https://example.com",
                "content": "Verified excerpt",
            }
        ],
    )
    assert (
        client.post("/api/search", json={"query": "test"}).json()[0]["title"]
        == "Test source"
    )
    result = client.post("/api/chat", json={"message": "test", "web": True}).json()
    assert "Verified excerpt" in result["answer"]
    assert len(result["sources"]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://localhost",
        "https://user:pass@example.com",
        "http://example.com:8080",
    ],
)
def test_private_urls_blocked(url):
    with pytest.raises(ValueError):
        web.validate_url(url)


def test_agent_workflow(client, monkeypatch):
    from happy.app import jobs, run_agent

    monkeypatch.setattr(
        web,
        "search",
        lambda q: [
            {"title": "Source", "url": "https://example.com", "content": "Excerpt"}
        ],
    )
    monkeypatch.setattr(web, "browse", lambda u: {"content": "Public page content"})
    jobs["test"] = {
        "id": "test",
        "topic": "Test topic",
        "status": "running",
        "steps": [],
        "sources": [],
    }
    run_agent("test", "Test topic")
    assert jobs["test"]["status"] == "complete"
    assert "Public page content" in jobs["test"]["result"]
    assert store.notes() == []  # Never save without approval.
    del jobs["test"]


def test_reader_pins_ip_and_strips_scripts(monkeypatch):
    import httpx

    def resolve(host, *args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(web.socket, "getaddrinfo", resolve)

    def handle(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<title>Example</title><script>bad()</script><main>Useful text</main>",
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(web.httpx, "Client", lambda **kwargs: client)
    result = web.browse("https://example.com")
    assert result["url"] == "https://example.com"
    assert "Useful text" in result["content"]
    assert "bad()" not in result["content"]


def test_redirect_to_private_network_blocked(monkeypatch):
    import httpx

    def resolve(host, *args, **kwargs):
        return [
            (
                2,
                1,
                6,
                "",
                ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443),
            )
        ]

    monkeypatch.setattr(web.socket, "getaddrinfo", resolve)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                302, headers={"location": "http://127.0.0.1/admin"}
            )
        )
    )
    monkeypatch.setattr(web.httpx, "Client", lambda **kwargs: client)
    with pytest.raises(ValueError, match="Private"):
        web.browse("https://example.com")


def test_backup_roundtrip_and_search(client):
    client.post(
        "/api/knowledge",
        json={"title": "Solar notes", "content": "Planets orbit stars"},
    )
    client.post("/api/knowledge", json={"title": "Recipes", "content": "Tomato soup"})
    assert len(client.get("/api/knowledge?q=solar").json()) == 1
    assert client.get("/api/knowledge?q=nonexistent").json() == []
    backup = client.get("/api/knowledge/export")
    assert "attachment" in backup.headers["content-disposition"]
    assert len(backup.json()["notes"]) == 2
    assert client.post("/api/knowledge/import", json=backup.json()).json() == {
        "added": 0
    }
    for n in client.get("/api/knowledge").json():
        client.delete("/api/knowledge/" + str(n["id"]))
    assert client.post("/api/knowledge/import", json=backup.json()).json() == {
        "added": 2
    }
    assert (
        client.post(
            "/api/knowledge/import", json={"version": 2, "notes": []}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/knowledge/import", json={"notes": [{"title": "", "content": "bad"}]}
        ).status_code
        == 422
    )
    assert len(client.get("/api/knowledge").json()) == 2


def test_persistent_conversation(client):
    assert client.get("/api/conversation").json() == []
    client.post("/api/chat", json={"message": "Hi Happy"})
    messages = client.get("/api/conversation").json()
    assert len(messages) == 2
    assert messages[0]["content"] == "Hi Happy"
    assert messages[1]["role"] == "assistant"
    assert len(store.conversation()) == 2
    assert client.delete("/api/conversation").status_code == 200
    assert store.conversation() == []


def test_blank_input_rejected(client):
    assert (
        client.post(
            "/api/knowledge", json={"title": "   ", "content": "  "}
        ).status_code
        == 422
    )
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/agents", json={"query": "   "}).status_code == 422


def test_retrieval_matches_words_not_substrings(client):
    store.save("Earth", "Our planet")
    assert store.retrieve("Tell me about art") == []
    assert store.retrieve("Earth?")[0]["title"] == "Earth"


def test_cancel_agent_and_persist(client, monkeypatch):
    from happy.app import jobs, run_agent

    jobs["cancel-test"] = {
        "id": "cancel-test",
        "status": "running",
        "topic": "test",
        "sources": [],
        "steps": [],
        "result": "",
    }
    assert (
        client.post("/api/agents/cancel-test/cancel").json()["status"] == "cancelling"
    )
    monkeypatch.setattr(
        web, "search", lambda q: pytest.fail("Cancelled workflow should not search")
    )
    run_agent("cancel-test", "test")
    assert jobs["cancel-test"]["status"] == "cancelled"
    assert store.research()[0]["status"] == "cancelled"
    assert client.post("/api/agents/not-found/cancel").status_code == 404


def test_restart_recovers_interrupted_research(client):
    store.save_job(
        {
            "id": "old",
            "topic": "interrupted",
            "status": "running",
            "sources": [],
            "steps": [],
            "result": "",
        }
    )
    with TestClient(app) as restarted:
        job = next(j for j in restarted.get("/api/agents").json() if j["id"] == "old")
        assert job["status"] == "interrupted"
        assert store.research()[0]["status"] == "interrupted"


def test_offline_research_uses_saved_knowledge(client, monkeypatch):
    from happy.app import jobs, run_agent

    store.save("Solar energy", "Solar panels convert sunlight into electricity.")
    monkeypatch.setattr(
        web, "search", lambda q: pytest.fail("Local research must not contact the web")
    )
    jobs["local"] = {
        "id": "local",
        "topic": "solar",
        "status": "running",
        "steps": [],
        "sources": [],
        "result": "",
    }
    run_agent("local", "solar", "knowledge")
    job = jobs["local"]
    assert job["status"] == "complete"
    assert "sunlight" in job["result"]
    assert len(job["sources"]) == 1
    assert "not an AI-generated answer" in job["result"]


def test_offline_research_reports_no_matches(client):
    from happy.app import jobs, run_agent

    jobs["empty"] = {
        "id": "empty",
        "topic": "solar",
        "status": "running",
        "steps": [],
        "sources": [],
        "result": "",
    }
    run_agent("empty", "solar", "knowledge")
    assert jobs["empty"]["status"] == "failed"
    assert "No matching saved notes" in jobs["empty"]["result"]


@pytest.mark.parametrize(
    "tool,text,other,expected",
    [
        ("calculator", "(125 * 4) / 10", "", "50.0"),
        ("json", '{"ok":true}', "", '"ok": true'),
        ("csv", "name,role\nHappy,Assistant", "", '"name": "Happy"'),
        ("stats", "Hello, world!", "", '"words": 2'),
        ("keywords", "solar solar panels", "", "solar: 2"),
        (
            "summary",
            "Solar panels absorb light. Solar energy powers homes.",
            "",
            "not AI-generated",
        ),
        ("diff", "old\n", "new\n", "-old"),
        ("base64-encode", "Happy", "", "SGFwcHk="),
        ("base64-decode", "SGFwcHk=", "", "Happy"),
        ("hash", "Happy", "", "" + __import__("hashlib").sha256(b"Happy").hexdigest()),
        ("url", "https://example.com?q=hello", "", '"hostname": "example.com"'),
        ("deduplicate", "one\ntwo\none", "", "one\ntwo"),
    ],
)
def test_offline_tools(client, tool, text, other, expected):
    result = client.post(
        "/api/tools/run", json={"tool": tool, "text": text, "other": other}
    )
    assert result.status_code == 200, result.text
    assert expected in result.json()["output"]
    assert result.json()["generated"] is False
    assert len(client.get("/api/tools").json()) == 12


@pytest.mark.parametrize(
    "text",
    [
        '__import__("os").system("id")',
        "2**1000000",
        "1/0",
        "[1,2]",
        "1e999",
        "(-1)**0.5",
    ],
)
def test_calculator_rejects_unsafe_or_excessive_input(client, text):
    assert (
        client.post(
            "/api/tools/run", json={"tool": "calculator", "text": text}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "tool,text",
    [
        ("json", '{"bad":}'),
        ("json", "NaN"),
        ("csv", "a,a\n1,2"),
        ("csv", "a,b\n1"),
        ("base64-decode", "not base64"),
        ("url", "not a url"),
    ],
)
def test_tool_errors(client, tool, text):
    assert (
        client.post("/api/tools/run", json={"tool": tool, "text": text}).status_code
        == 422
    )


def test_knowledge_edit(client):
    note = client.post(
        "/api/knowledge", json={"title": "Old", "content": "Original", "source": "Book"}
    ).json()
    response = client.put(
        "/api/knowledge/" + str(note["id"]),
        json={"title": "Updated", "content": "Revised", "source": "Book"},
    )
    assert response.status_code == 200
    stored = client.get("/api/knowledge").json()[0]
    assert stored["title"] == "Updated" and stored["source"] == "Book"
    assert (
        client.put(
            "/api/knowledge/999", json={"title": "Missing", "content": "Nothing"}
        ).status_code
        == 404
    )


def test_agent_delete_and_retry(client, monkeypatch):
    from happy.app import jobs

    store.save("Solar", "Solar energy")
    jobs["old"] = {
        "id": "old",
        "topic": "Solar",
        "source": "knowledge",
        "status": "complete",
        "sources": [],
        "steps": [],
        "result": "Done",
    }
    store.save_job(jobs["old"])
    # Hold execution so retry state is deterministic, without touching real threads.
    monkeypatch.setattr("happy.app.run_agent", lambda *args: None)
    retried = client.post("/api/agents/old/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] != "old"
    assert retried.json()["source"] == "knowledge"
    new_id = retried.json()["id"]
    assert client.delete("/api/agents/" + new_id).status_code == 409
    assert client.post("/api/agents/" + new_id + "/retry").status_code == 409
    assert client.delete("/api/agents/old").status_code == 200
    assert all(j["id"] != "old" for j in store.research())
    assert client.delete("/api/agents/missing").status_code == 404


def test_password_protection(client, monkeypatch):
    from happy import security

    security.attempts.clear()
    security.sessions.clear()
    monkeypatch.setenv("HAPPY_PASSWORD", "test-workspace-password")
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/knowledge").status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/login").status_code == 200
    assert client.post("/auth/login", json={"password": "wrong"}).status_code == 401
    result = client.post("/auth/login", json={"password": "test-workspace-password"})
    assert result.status_code == 200
    assert "httponly" in result.headers["set-cookie"].lower()
    assert "samesite=strict" in result.headers["set-cookie"].lower()
    assert client.get("/api/knowledge").status_code == 200
    assert client.get("/auth/status").json()["authenticated"] is True
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/api/knowledge").status_code == 401


def test_login_rate_limit(client, monkeypatch):
    from happy import security

    security.attempts.clear()
    monkeypatch.setenv("HAPPY_PASSWORD", "test-password")
    for _ in range(10):
        assert client.post("/auth/login", json={"password": "wrong"}).status_code == 401
    assert (
        client.post("/auth/login", json={"password": "test-password"}).status_code
        == 429
    )
    security.attempts.clear()


def test_security_headers_origin_and_body_limits(client):
    result = client.get("/")
    assert result.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in result.headers["content-security-policy"]
    assert (
        client.post(
            "/api/knowledge",
            json={"title": "X", "content": "X"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/knowledge",
            json={"title": "X", "content": "X"},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 200
    )
    assert client.post("/api/chat", content=b"x" * (129 * 1024)).status_code == 413
