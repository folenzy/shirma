import json

import httpx
import pytest
from fastapi.testclient import TestClient

from shirma.app import create_app
from shirma.config import Settings

PROMPT = "Подготовь письмо для Петра Иванова, его телефон +7 916 123-45-67."


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(upstream_url="mock", demo=True))) as c:
        yield c


def _chat(stream: bool) -> dict:
    return {"model": "mock", "stream": stream, "messages": [{"role": "user", "content": PROMPT}]}


def test_non_stream_restores_answer(client):
    r = client.post("/v1/chat/completions", json=_chat(False))
    assert r.status_code == 200
    answer = r.json()["choices"][0]["message"]["content"]
    assert "Петра Иванова" in answer and "+7 916 123-45-67" in answer
    assert "[PER_1]" not in answer
    assert r.headers["x-shirma-masked"] == "PER=1,PHONE=1"


def test_stream_restores_answer(client):
    text = ""
    with client.stream("POST", "/v1/chat/completions", json=_chat(True)) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                for choice in json.loads(line[6:])["choices"]:
                    text += choice["delta"].get("content") or ""
    non_stream = client.post("/v1/chat/completions", json=_chat(False)).json()
    assert text == non_stream["choices"][0]["message"]["content"]


def test_demo_mask_endpoint(client):
    data = client.post("/api/mask", json={"text": PROMPT}).json()
    assert data["masked"] == "Подготовь письмо для [PER_1], его телефон [PHONE_1]."


def _capturing_app(seen: list[httpx.Request], status: int = 200, settings: Settings | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "bad key"}})
        body = json.loads(request.content)
        content = body["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]},
        )

    settings = settings or Settings(upstream_url="http://upstream/v1", demo=False)
    return create_app(settings, transport=httpx.MockTransport(handler))


def test_upstream_never_sees_personal_data():
    seen: list[httpx.Request] = []
    with TestClient(_capturing_app(seen)) as c:
        r = c.post(
            "/v1/chat/completions", json=_chat(False), headers={"Authorization": "Bearer sk-client"}
        )
    sent = seen[0].content.decode()
    assert "Иванов" not in sent and "123-45-67" not in sent
    assert seen[0].headers["authorization"] == "Bearer sk-client"
    assert seen[0].url.path == "/v1/chat/completions"
    # Модель вернула текст с метками — клиент получил исходник (имя — в именительном).
    assert r.json()["choices"][0]["message"]["content"] == (
        "Подготовь письмо для Петра Иванова, его телефон +7 916 123-45-67."
    )


def test_hint_is_injected_only_when_something_was_masked():
    seen: list[httpx.Request] = []
    with TestClient(_capturing_app(seen)) as c:
        c.post("/v1/chat/completions", json=_chat(False))
        c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "Привет"}]},
        )
    roles = [[m["role"] for m in json.loads(r.content)["messages"]] for r in seen]
    assert roles == [["system", "user"], ["user"]]


def test_server_key_overrides_client_key():
    seen: list[httpx.Request] = []
    settings = Settings(upstream_url="http://upstream/v1", upstream_api_key="sk-server", demo=False)
    with TestClient(_capturing_app(seen, settings=settings)) as c:
        c.post(
            "/v1/chat/completions", json=_chat(False), headers={"Authorization": "Bearer sk-client"}
        )
    assert seen[0].headers["authorization"] == "Bearer sk-server"


def test_upstream_error_is_passed_through():
    seen: list[httpx.Request] = []
    with TestClient(_capturing_app(seen, status=401)) as c:
        r = c.post("/v1/chat/completions", json=_chat(False))
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "bad key"


def test_bad_body_is_400_not_500(client):
    cp1251 = '{"messages": [{"role": "user", "content": "Привет"}]}'.encode("cp1251")
    assert client.post("/v1/chat/completions", content=cp1251).status_code == 400
    assert client.post("/v1/chat/completions", content=b"[1, 2]").status_code == 400


def test_demo_is_off_when_disabled():
    with TestClient(_capturing_app([])) as c:
        assert c.get("/").status_code == 404
        assert c.post("/api/mask", json={"text": "x"}).status_code == 404
