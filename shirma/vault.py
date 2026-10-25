"""Сопоставление «значение ↔ метка» на время одного запроса.

Хранилище живёт в памяти только пока идёт запрос: метки детерминированы
по порядку появления, поэтому в диалоге с историей [PER_1] остаётся [PER_1]
от сообщения к сообщению, а на диск ничего не пишется.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from .detect import Detector, Kind, Span
from .morph import Person, guess_case
from .policy import Policy

PLACEHOLDER = re.compile(r"\[(" + "|".join(k.value for k in Kind) + r")_(\d{1,4})\]")
# Самая длинная возможная метка: [ADDRESS_9999]
PLACEHOLDER_MAX_LEN = max(len(k.value) for k in Kind) + 7


@dataclass
class Entity:
    kind: Kind
    number: int
    original: str
    person: Person | None = None

    @property
    def placeholder(self) -> str:
        return f"[{self.kind.value}_{self.number}]"

    def render(self, before: str, restore_case: bool) -> str:
        if self.person is None:
            return self.original
        return self.person.render(guess_case(before) if restore_case else "nomn")


def _key(kind: Kind, value: str) -> str:
    if kind in (Kind.PHONE,):
        return re.sub(r"\D", "", value)[-10:]
    if kind in (Kind.INN, Kind.SNILS, Kind.CARD, Kind.PASSPORT, Kind.ACCOUNT):
        return re.sub(r"\D", "", value)
    return " ".join(value.casefold().replace("ё", "е").split()).strip("«»\"' ")


@dataclass
class Vault:
    detector: Detector
    policy: Policy
    _entities: dict[str, Entity] = field(default_factory=dict)
    _by_key: dict[tuple[Kind, str], Entity] = field(default_factory=dict)
    _counters: Counter = field(default_factory=Counter)

    def mask(self, text: str) -> tuple[str, list[tuple[Span, Entity]]]:
        spans = [
            s for s in self.detector.find(text, self.policy.mask) if not self.policy.allowed(s.text)
        ]
        out, pos, found = [], 0, []
        for span in spans:
            entity = self._entity_for(span)
            out += [text[pos : span.start], entity.placeholder]
            pos = span.stop
            found.append((span, entity))
        out.append(text[pos:])
        return "".join(out), found

    def _entity_for(self, span: Span) -> Entity:
        if span.kind is Kind.PER:
            return self._person_for(span)
        key = (span.kind, _key(span.kind, span.text))
        if key not in self._by_key:
            self._by_key[key] = self._new(span.kind, span.text)
        return self._by_key[key]

    def _person_for(self, span: Span) -> Entity:
        mention = Person.from_text(span.text)
        for entity in self._entities.values():
            if entity.person is not None and entity.person.same_as(mention):
                entity.person.absorb(mention)
                return entity
        entity = self._new(Kind.PER, span.text)
        entity.person = mention
        return entity

    def _new(self, kind: Kind, original: str) -> Entity:
        self._counters[kind] += 1
        entity = Entity(kind, self._counters[kind], original)
        self._entities[entity.placeholder] = entity
        return entity

    def restore(
        self, text: str, already: str = "", escape: Callable[[str], str] | None = None
    ) -> str:
        """Подставляет значения вместо меток. already — то, что уже ушло клиенту
        перед этим текстом: по нему определяется падеж в начале куска.
        escape — для подстановки внутрь JSON-строки (аргументы tool calls)."""
        out, pos = [], 0
        for m in PLACEHOLDER.finditer(text):
            entity = self._entities.get(m.group())
            if entity is None:
                continue  # модель выдумала метку — оставляем как есть
            out.append(text[pos : m.start()])
            before = already + "".join(out)
            value = entity.render(before, self.policy.restore_case)
            out.append(escape(value) if escape else value)
            pos = m.end()
        out.append(text[pos:])
        return "".join(out)

    def stats(self) -> dict[str, int]:
        return {k.value: n for k, n in self._counters.items()}

    def table(self) -> dict[str, str]:
        return {p: e.original for p, e in self._entities.items()}
