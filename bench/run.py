"""Замер качества и скорости маскирования на синтетическом корпусе.

python -m bench.run --n 1000          # печатает таблицу и пишет bench/RESULTS.md
"""

import argparse
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from shirma.detect import Detector, Kind, Span
from shirma.policy import DEFAULT_MASK

from .corpus import Generator, Gold, Sample


@dataclass
class Report:
    docs: int = 0
    gold: Counter = field(default_factory=Counter)
    found: Counter = field(default_factory=Counter)  # нашли и правильно назвали тип
    hidden: Counter = field(default_factory=Counter)  # значение целиком скрыто (тип не важен)
    predicted: Counter = field(default_factory=Counter)
    correct: Counter = field(default_factory=Counter)
    false_masks: list[str] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    chars: int = 0

    def add(self, sample: Sample, spans: list[Span], ms: float) -> None:
        self.docs += 1
        self.chars += len(sample.text)
        self.latencies_ms.append(ms)
        for g in sample.gold:
            self.gold[g.kind] += 1
            if any(s.kind is g.kind and _overlap(s, g) for s in spans):
                self.found[g.kind] += 1
            if _covered(g, spans):
                self.hidden[g.kind] += 1
            else:
                self.leaks.append(f"{g.kind}: {g.text!r} в «{sample.text}»")
        for s in spans:
            self.predicted[s.kind] += 1
            if any(s.kind is g.kind and _overlap(s, g) for g in sample.gold):
                self.correct[s.kind] += 1
            elif not any(_overlap(s, g) for g in sample.gold):
                self.false_masks.append(f"{s.kind}: {s.text!r}")

    def markdown(self) -> str:
        rows = [
            "| Тип | Значений | Скрыто полностью | Полнота (тип верен) | Точность |",
            "|---|---:|---:|---:|---:|",
        ]
        for kind in sorted(self.gold, key=lambda k: -self.gold[k]):
            g = self.gold[kind]
            prec = self.correct[kind] / self.predicted[kind] if self.predicted[kind] else 0.0
            rows.append(
                f"| {kind} | {g} | {self.hidden[kind] / g:.1%} | {self.found[kind] / g:.1%} | {prec:.1%} |"
            )
        total = sum(self.gold.values())
        lat = sorted(self.latencies_ms)
        p95 = lat[int(len(lat) * 0.95) - 1]
        summary = [
            f"- Документов: **{self.docs}**, значений ПДн: **{total}**",
            f"- Скрыто полностью: **{sum(self.hidden.values()) / total:.1%}** "
            f"(утекло {total - sum(self.hidden.values())})",
            f"- Ложных срабатываний: **{len(self.false_masks)}** на {self.docs} документов",
            f"- Время маскирования: p50 **{statistics.median(lat):.1f} мс**, p95 **{p95:.1f} мс** "
            f"на документ (~{self.chars // self.docs} символов), CPU, один поток",
        ]
        return "\n".join(summary) + "\n\n" + "\n".join(rows) + "\n"


def _overlap(s: Span, g: Gold) -> bool:
    return s.start < g.stop and g.start < s.stop


def _covered(g: Gold, spans: list[Span]) -> bool:
    chars = set(range(g.start, g.stop))
    for s in spans:
        chars -= set(range(s.start, s.stop))
    # Пробелы и пунктуация по краям значения — не утечка.
    return all(not g.text[i - g.start].isalnum() for i in chars)


def evaluate(n: int, seed: int = 42, detector: Detector | None = None) -> Report:
    detector = detector or Detector()
    detector.ner.warm_up()
    report = Report()
    for sample in Generator(seed).corpus(n):
        t0 = time.perf_counter()
        spans = detector.find(sample.text, DEFAULT_MASK)
        report.add(sample, spans, (time.perf_counter() - t0) * 1000)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--show", type=int, default=15, help="сколько утечек и ложных срабатываний показать"
    )
    args = parser.parse_args()

    report = evaluate(args.n, args.seed)
    md = report.markdown()
    print(md)
    for title, items in (("Утечки", report.leaks), ("Ложные срабатывания", report.false_masks)):
        print(f"{title} ({len(items)}):")
        for line in items[: args.show]:
            print("  ", line)
    out = Path(__file__).with_name("RESULTS.md")
    out.write_text(
        f"# Результаты бенчмарка\n\nКорпус: `python -m bench.run --n {args.n} --seed {args.seed}`\n\n{md}",
        encoding="utf-8",
    )
    print(f"\nЗаписано в {out}")


if __name__ == "__main__":
    main()

__all__ = ["Kind", "evaluate"]
