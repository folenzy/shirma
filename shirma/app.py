import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from importlib.resources import files

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import __version__, mock_upstream
from .config import Settings
from .detect import Detector
from .policy import Policy
from .proxy import mask_request, restore_response
from .stream import ChatStreamRewriter
from .vault import Vault

audit = logging.getLogger("shirma.audit")

_FORWARD_HEADERS = ("authorization", "openai-organization", "openai-project", "accept")


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or Settings()
    policy = Policy.load(settings.policy)
    detector = Detector()

    if settings.upstream_url == "mock":
        base_url, transport = (
            "http://mock/v1",
            transport or httpx.ASGITransport(app=mock_upstream.app),
        )
    else:
        base_url = settings.upstream_url.rstrip("/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(detector.ner.warm_up)
        async with httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=settings.timeout
        ) as client:
            app.state.client = client
            yield

    app = FastAPI(title="Ширма", version=__version__, lifespan=lifespan)

    def upstream_headers(request: Request) -> dict[str, str]:
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_HEADERS}
        if settings.upstream_api_key:
            headers["authorization"] = f"Bearer {settings.upstream_api_key}"
        return headers

    def log(request_id: str, vault: Vault, **extra) -> None:
        # Только счётчики и тайминги — ни одного значения.
        audit.info(
            json.dumps({"id": request_id, "masked": vault.stats(), **extra}, ensure_ascii=False)
        )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "version": __version__, "upstream": base_url}

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        r = await app.state.client.get("/models", headers=upstream_headers(request))
        return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError as e:  # битый JSON или не UTF-8
            raise HTTPException(400, "тело запроса — не JSON в UTF-8") from e
        if not isinstance(body, dict):
            raise HTTPException(400, "тело запроса должно быть JSON-объектом")

        request_id = uuid.uuid4().hex[:12]
        vault = Vault(detector, policy)
        t0 = time.perf_counter()
        masked = await run_in_threadpool(mask_request, vault, body)
        mask_ms = round((time.perf_counter() - t0) * 1000, 1)
        headers = {"x-shirma-request-id": request_id, "x-shirma-masked": _stats_header(vault)}
        client: httpx.AsyncClient = app.state.client

        if not body.get("stream"):
            r = await client.post(
                "/chat/completions", json=masked, headers=upstream_headers(request)
            )
            log(
                request_id,
                vault,
                model=body.get("model"),
                stream=False,
                mask_ms=mask_ms,
                status=r.status_code,
            )
            if r.status_code >= 400:
                return Response(
                    r.content, r.status_code, headers, media_type=r.headers.get("content-type")
                )
            return JSONResponse(restore_response(vault, r.json()), headers=headers)

        upstream_req = client.build_request(
            "POST", "/chat/completions", json=masked, headers=upstream_headers(request)
        )
        r = await client.send(upstream_req, stream=True)
        log(
            request_id,
            vault,
            model=body.get("model"),
            stream=True,
            mask_ms=mask_ms,
            status=r.status_code,
        )
        if r.status_code >= 400:
            content = await r.aread()
            await r.aclose()
            return Response(
                content, r.status_code, headers, media_type=r.headers.get("content-type")
            )

        async def events():
            try:
                async for chunk in ChatStreamRewriter(vault).rewrite(r.aiter_lines()):
                    yield chunk
            finally:
                await r.aclose()

        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    if settings.demo:
        _mount_demo(app, detector, policy, upstream_headers)

    return app


def _stats_header(vault: Vault) -> str:
    return ",".join(f"{k}={n}" for k, n in sorted(vault.stats().items()))


class MaskIn(BaseModel):
    text: str


class ChatIn(BaseModel):
    messages: list[dict]
    model: str = "mock"


def _mount_demo(app: FastAPI, detector: Detector, policy: Policy, upstream_headers) -> None:
    page = files("shirma").joinpath("static/index.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        return page

    @app.post("/api/mask")
    async def api_mask(payload: MaskIn) -> dict:
        vault = Vault(detector, policy)
        t0 = time.perf_counter()
        masked, found = await run_in_threadpool(vault.mask, payload.text)
        return {
            "masked": masked,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "entities": [
                {
                    "placeholder": e.placeholder,
                    "kind": s.kind,
                    "text": s.text,
                    "start": s.start,
                    "stop": s.stop,
                }
                for s, e in found
            ],
        }

    @app.post("/api/chat")
    async def api_chat(payload: ChatIn, request: Request) -> dict:
        """То же, что /v1/chat/completions, но показывает все три стадии."""
        vault = Vault(detector, policy)
        body = {"model": payload.model, "messages": payload.messages}
        masked = await run_in_threadpool(mask_request, vault, body)
        r = await app.state.client.post(
            "/chat/completions", json=masked, headers=upstream_headers(request)
        )
        if r.status_code >= 400:
            raise HTTPException(502, f"модель ответила {r.status_code}: {r.text[:300]}")
        raw = r.json()["choices"][0]["message"]["content"]
        return {
            "sent_to_model": masked["messages"],
            "model_answer": raw,
            "answer": vault.restore(raw),
            "table": vault.table(),
        }
