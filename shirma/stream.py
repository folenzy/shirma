"""Обратная подстановка в потоковом ответе.

Модель отдаёт текст кусками по несколько символов, и метка может прийти
разорванной: «...для [PE» + «R_1] к пятнице». Отдавать клиенту «[PE» нельзя —
он увидит обрывок метки, а значение уже не подставится. Поэтому хвост, который
может оказаться началом метки, придерживаем до следующего куска. Задержка —
не больше длины самой длинной метки, остальной текст уходит сразу.
"""

import json
import re
from collections.abc import AsyncIterator, Callable

from .vault import PLACEHOLDER_MAX_LEN, Vault

_PARTIAL = re.compile(r"\[[A-Z]*(?:_\d*)?")


def safe_cut(buf: str) -> int:
    """Позиция, до которой буфер можно отдать: дальше может начинаться метка."""
    i = buf.rfind("[")
    if i == -1:
        return len(buf)
    tail = buf[i:]
    if len(tail) < PLACEHOLDER_MAX_LEN and _PARTIAL.fullmatch(tail):
        return i
    return len(buf)


class StreamRestorer:
    def __init__(self, vault: Vault, escape: Callable[[str], str] | None = None) -> None:
        self._vault = vault
        self._escape = escape
        self._pending = ""
        self._tail = ""  # последние символы, ушедшие клиенту, — для угадывания падежа

    def feed(self, chunk: str) -> str:
        buf = self._pending + chunk
        cut = safe_cut(buf)
        self._pending = buf[cut:]
        return self._emit(buf[:cut])

    def flush(self) -> str:
        ready, self._pending = self._pending, ""
        return self._emit(ready)

    def _emit(self, text: str) -> str:
        if not text:
            return ""
        out = self._vault.restore(text, already=self._tail, escape=self._escape)
        self._tail = (self._tail + out)[-40:]
        return out


def json_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


class ChatStreamRewriter:
    """Переписывает SSE-поток /v1/chat/completions в формате OpenAI."""

    def __init__(self, vault: Vault) -> None:
        self._vault = vault
        self._restorers: dict[tuple, StreamRestorer] = {}
        self._last: dict | None = None

    def _restorer(self, key: tuple, escape=None) -> StreamRestorer:
        if key not in self._restorers:
            self._restorers[key] = StreamRestorer(self._vault, escape)
        return self._restorers[key]

    def rewrite_event(self, event: dict) -> dict:
        for choice in event.get("choices") or []:
            idx = choice.get("index", 0)
            delta = choice.get("delta") or {}
            final = choice.get("finish_reason") is not None
            if isinstance(delta.get("content"), str) or final:
                r = self._restorer(("content", idx))
                text = r.feed(delta.get("content") or "")
                if final:
                    text += r.flush()
                if text or "content" in delta:
                    delta["content"] = text
                    choice["delta"] = delta
            for call in delta.get("tool_calls") or []:
                fn = call.get("function") or {}
                if isinstance(fn.get("arguments"), str):
                    r = self._restorer(("tool", idx, call.get("index", 0)), json_escape)
                    fn["arguments"] = r.feed(fn["arguments"])
            if final:
                for key, r in self._restorers.items():
                    if key[0] == "tool" and key[1] == idx:
                        self._flush_tool_into(choice, key[2], r.flush())
        self._last = event
        return event

    @staticmethod
    def _flush_tool_into(choice: dict, call_index: int, rest: str) -> None:
        if not rest:
            return
        delta = choice.setdefault("delta", {})
        delta.setdefault("tool_calls", []).append(
            {"index": call_index, "function": {"arguments": rest}}
        )

    def leftovers(self) -> dict | None:
        """Если поток кончился без finish_reason, досылаем придержанный хвост."""
        choices = []
        for key, r in self._restorers.items():
            rest = r.flush()
            if not rest:
                continue
            if key[0] == "content":
                choices.append({"index": key[1], "delta": {"content": rest}, "finish_reason": None})
            else:
                choice = {"index": key[1], "delta": {}, "finish_reason": None}
                self._flush_tool_into(choice, key[2], rest)
                choices.append(choice)
        if not choices:
            return None
        base = {
            k: v for k, v in (self._last or {}).items() if k in ("id", "object", "created", "model")
        }
        return {**base, "choices": choices}

    async def rewrite(self, lines: AsyncIterator[str]) -> AsyncIterator[bytes]:
        async for line in lines:
            if not line.startswith("data:"):
                if line:
                    yield (line + "\n").encode()
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                tail = self.leftovers()
                if tail:
                    yield _sse(tail)
                yield b"data: [DONE]\n\n"
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                yield (line + "\n\n").encode()
                continue
            yield _sse(self.rewrite_event(event))
        tail = self.leftovers()
        if tail:
            yield _sse(tail)


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
