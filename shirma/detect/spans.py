from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    PER = "PER"
    ORG = "ORG"
    LOC = "LOC"
    ADDRESS = "ADDRESS"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    INN = "INN"
    SNILS = "SNILS"
    CARD = "CARD"
    PASSPORT = "PASSPORT"
    ACCOUNT = "ACCOUNT"


# Чем выше, тем важнее при пересечении: ИНН внутри адреса остаётся ИНН,
# а улица, которую NER принял за персону, остаётся адресом.
PRIORITY: dict[Kind, int] = {
    Kind.EMAIL: 100,
    Kind.CARD: 90,
    Kind.SNILS: 90,
    Kind.INN: 90,
    Kind.ACCOUNT: 85,
    Kind.PASSPORT: 85,
    Kind.PHONE: 80,
    Kind.ADDRESS: 60,
    Kind.PER: 50,
    Kind.ORG: 40,
    Kind.LOC: 30,
}


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    stop: int
    kind: Kind
    text: str

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.stop and other.start < self.stop


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Оставляет непересекающиеся фрагменты: сначала важные, затем длинные."""
    ranked = sorted(spans, key=lambda s: (-PRIORITY[s.kind], -(s.stop - s.start), s.start))
    kept: list[Span] = []
    for span in ranked:
        if not any(span.overlaps(k) for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)
