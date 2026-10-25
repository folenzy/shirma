"""Главное свойство потока: как бы модель ни нарезала ответ на куски,
клиент получает ровно тот же текст, что и при ответе целиком."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from shirma.detect import Detector
from shirma.policy import Policy
from shirma.stream import ChatStreamRewriter, StreamRestorer, safe_cut
from shirma.vault import Vault

SOURCE = "Поручить Петру Иванову, тел. +7 916 123-45-67, почта p.ivanov@mail.ru, ИНН 7707083893."
ANSWERS = st.lists(
    st.sampled_from(
        [
            "[PER_1]",
            "[PHONE_1]",
            "[EMAIL_1]",
            "[INN_1]",
            "[PER_9]",
            "[",
            "]",
            "[PER_",
            "для ",
            "с ",
            "текст ",
            "[[",
            "Ответ: ",
            "\n",
            "ё",
        ]
    ),
    max_size=30,
).map("".join)


def _vault(detector: Detector) -> Vault:
    vault = Vault(detector, Policy())
    vault.mask(SOURCE)
    return vault


def _split(text: str, cuts: list[int]) -> list[str]:
    points = sorted({c % (len(text) + 1) for c in cuts})
    return [text[a:b] for a, b in zip([0, *points], [*points, len(text)], strict=True)]


@settings(max_examples=300, deadline=None)
@given(answer=ANSWERS, cuts=st.lists(st.integers(min_value=0, max_value=400), max_size=40))
def test_any_chunking_gives_same_text(detector, answer, cuts):
    vault = _vault(detector)
    restorer = StreamRestorer(vault)
    streamed = "".join(restorer.feed(c) for c in _split(answer, cuts)) + restorer.flush()
    assert streamed == vault.restore(answer)


def test_safe_cut_holds_only_possible_placeholder_prefix():
    assert safe_cut("для [PE") == len("для ")
    assert safe_cut("для [PER_1") == len("для ")
    assert safe_cut("массив [1, 2]") == len("массив [1, 2]")
    assert safe_cut("см. [примечание") == len("см. [примечание")
    assert safe_cut("[" + "A" * 30) == 31


def test_sse_rewrite_handles_split_placeholder(detector):
    vault = _vault(detector)
    rewriter = ChatStreamRewriter(vault)
    pieces = ["Письмо для [PE", "R_1] на [EMA", "IL_1]"]
    events = [
        {"choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]} for p in pieces
    ]
    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    out = "".join(
        rewriter.rewrite_event(e)["choices"][0]["delta"].get("content", "") for e in events
    )
    assert out == "Письмо для Петра Иванова на p.ivanov@mail.ru"


def test_tool_call_arguments_are_json_escaped(detector):
    vault = Vault(detector, Policy())
    vault.mask('Договор с ООО "Ромашка"')
    rewriter = ChatStreamRewriter(vault)
    args = ""
    for piece in ['{"org": "[OR', 'G_1]"}']:
        event = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": piece}}]},
                    "finish_reason": None,
                }
            ]
        }
        args += rewriter.rewrite_event(event)["choices"][0]["delta"]["tool_calls"][0]["function"][
            "arguments"
        ]
    assert json.loads(args) == {"org": 'ООО "Ромашка"'}
