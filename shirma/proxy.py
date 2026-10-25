"""Маскирование запроса и восстановление ответа в формате OpenAI Chat Completions."""

import copy
import json
from typing import Any

from .policy import HINT
from .stream import json_escape
from .vault import Vault


def mask_request(vault: Vault, body: dict) -> dict:
    """Копия тела запроса, в которой все тексты сообщений прошли через маску."""
    body = copy.deepcopy(body)
    for message in body.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = vault.mask(content)[0]
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    part["text"] = vault.mask(part["text"])[0]
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            if isinstance(fn.get("arguments"), str):
                fn["arguments"] = _mask_json_string(vault, fn["arguments"])
    if vault.stats() and vault.policy.inject_hint:
        body["messages"] = [{"role": "system", "content": HINT}, *body.get("messages", [])]
    return body


def restore_response(vault: Vault, body: dict) -> dict:
    for choice in body.get("choices") or []:
        message = choice.get("message") or {}
        if isinstance(message.get("content"), str):
            message["content"] = vault.restore(message["content"])
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            if isinstance(fn.get("arguments"), str):
                fn["arguments"] = vault.restore(fn["arguments"], escape=json_escape)
    return body


def _mask_json_string(vault: Vault, raw: str) -> str:
    """Аргументы tool call — JSON в строке. Маскируем строковые значения,
    чтобы не сломать кавычки и экранирование."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return vault.mask(raw)[0]

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return vault.mask(node)[0]
        if isinstance(node, list):
            return [walk(x) for x in node]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    return json.dumps(walk(data), ensure_ascii=False)
