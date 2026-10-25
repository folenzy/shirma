"""Имена, организации и места — нейросетевой NER Natasha, локально, без сети.

Модели лежат внутри пакета natasha (~30 МБ) и грузятся один раз при первом вызове.
"""

import re
import threading
from functools import cached_property

from ..morph import has_patronymic, is_common_word, is_function_word, is_name_word
from .spans import Kind, Span

_NER_KINDS = {"PER": Kind.PER, "ORG": Kind.ORG, "LOC": Kind.LOC}


class NerDetector:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    @cached_property
    def _models(self):
        from natasha import NewsEmbedding, NewsNERTagger, Segmenter

        return Segmenter(), NewsNERTagger(NewsEmbedding())

    def warm_up(self) -> None:
        self.find("Иван Петров", {Kind.PER})

    def find(self, text: str, kinds: set[Kind]) -> list[Span]:
        if not {Kind.PER, Kind.ORG, Kind.LOC} & kinds or not text.strip():
            return []
        from natasha import Doc

        with self._lock:
            segmenter, tagger = self._models
            doc = Doc(text)
            doc.segment(segmenter)
            doc.tag_ner(tagger)
        spans = []
        for raw in doc.spans:
            span = _fix_kind(Span(raw.start, raw.stop, _NER_KINDS[raw.type], raw.text))
            if span is not None and span.kind is Kind.PER:
                span = _trim_person(span)
            if span is not None:
                spans.append(span)
        spans = _merge_adjacent_persons(text, spans)
        spans = [_extend_person(text, s) if s.kind is Kind.PER else s for s in spans]
        return [s for s in spans if s.kind in kinds]


_WORD = re.compile(r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?")
_NEXT_WORD = re.compile(r" ([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)")
_PREV_WORD = re.compile(r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?) $")


def _fix_kind(span: Span) -> Span | None:
    """«Согласовано с Фомичёвым» NER считает местом. Если словарь уверен,
    что это фамилия или имя, — это человек. А «Банк» или «Перезвони» с большой
    буквы в начале фразы — обычные слова, а не организация."""
    single = _WORD.fullmatch(span.text) is not None
    if span.kind is Kind.LOC and single and is_name_word(span.text):
        return Span(span.start, span.stop, Kind.PER, span.text)
    if span.kind is Kind.ORG and single and is_common_word(span.text):
        return None
    return span


def _trim_person(span: Span) -> Span | None:
    """Срезаем прилипшие к имени служебные слова и глаголы: «[Напомните
    Лыткиной]» → «Лыткиной». Существительные не трогаем: редкую фамилию
    словарь может не знать, и срезать её — значит выпустить наружу.
    Если остались одни глаголы («Подготовь» в начале фразы) — это не имя."""
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", span.text)]
    names = [not is_function_word(span.text[a:b].strip(".,")) for a, b in words]
    if not any(names):
        return None
    first = names.index(True)
    last = len(names) - 1 - names[::-1].index(True)
    a, b = words[first][0], words[last][1]
    return Span(span.start + a, span.start + b, Kind.PER, span.text[a:b])


def _extend_person(text: str, span: Span) -> Span:
    """NER часто теряет фамилию или отчество с края: «Встреча с [Валентиной
    Кузьминичной] Одинцовой». Добираем соседние слова с большой буквы,
    если словарь знает их как имя, фамилию или отчество. Не больше трёх слов.
    Рядом с отчеством берём и редкие имена, совпадающие с обычными словами
    («Олимпиада Дмитриевна»)."""
    start, stop = span.start, span.stop
    while len(text[start:stop].split()) < 3:
        lenient = has_patronymic(text[start:stop])
        m = _NEXT_WORD.match(text, stop)
        if m and is_name_word(m.group(1), lenient):
            stop = m.end()
            continue
        m = _PREV_WORD.search(text, 0, start)
        if m and m.end() == start and is_name_word(m.group(1), lenient):
            start = m.start()
            continue
        break
    if (start, stop) == (span.start, span.stop):
        return span
    return Span(start, stop, Kind.PER, text[start:stop])


def _merge_adjacent_persons(text: str, spans: list[Span]) -> list[Span]:
    """NER иногда режет «Анны Сергеевны Котовой» на два фрагмента — склеиваем."""
    merged: list[Span] = []
    for span in sorted(spans, key=lambda s: s.start):
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev.kind is Kind.PER
            and span.kind is Kind.PER
            and text[prev.stop : span.start].isspace()
        ):
            merged[-1] = Span(prev.start, span.stop, Kind.PER, text[prev.start : span.stop])
        else:
            merged.append(span)
    return merged
