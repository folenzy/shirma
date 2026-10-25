"""Учебная «модель» с API как у OpenAI: отвечает по шаблону и упоминает
все метки из последнего сообщения. Нужна, чтобы шлюз можно было показать
и протестировать без ключей и без сети. Поток режет на куски по 3 символа —
так метки гарантированно рвутся между кусками."""

import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .vault import PLACEHOLDER

CHUNK = 3

app = FastAPI(title="mock upstream")


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if p.get("type") == "text")
            return content or ""
    return ""


def compose_answer(messages: list[dict]) -> str:
    seen = list(dict.fromkeys(m.group() for m in PLACEHOLDER.finditer(_last_user_text(messages))))
    if not seen:
        return "Персональных данных в запросе не вижу — отвечаю как обычно."
    people = [p for p in seen if p.startswith("[PER_")]
    parts = [f"Принято. Модель получила только метки: {', '.join(seen)}."]
    if people:
        parts.append(f"Подготовлю письмо для {people[0]} и созвонюсь с {people[0]}.")
        parts.append(f"Ответственный — {people[-1]}.")
    return " ".join(parts)


def _chunk(cid: str, model: str, delta: dict, finish: str | None = None) -> str:
    event = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/v1/models")
async def models() -> dict:
    return {"object": "list", "data": [{"id": "mock", "object": "model", "owned_by": "shirma"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    model = body.get("model", "mock")
    answer = compose_answer(body.get("messages", []))
    cid = "chatcmpl-mock"
    if not body.get("stream"):
        return JSONResponse(
            {
                "id": cid,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        )

    def events():
        yield _chunk(cid, model, {"role": "assistant", "content": ""})
        for i in range(0, len(answer), CHUNK):
            yield _chunk(cid, model, {"content": answer[i : i + CHUNK]})
        yield _chunk(cid, model, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
