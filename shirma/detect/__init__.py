from .ner import NerDetector
from .patterns import find_patterns
from .spans import Kind, Span, resolve_overlaps

__all__ = ["Detector", "Kind", "Span"]


class Detector:
    def __init__(self, ner: NerDetector | None = None) -> None:
        self.ner = ner or NerDetector()

    def find(self, text: str, kinds: set[Kind]) -> list[Span]:
        spans = find_patterns(text, kinds) + self.ner.find(text, kinds)
        return resolve_overlaps(spans)
