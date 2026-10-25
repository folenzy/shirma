"""Порог качества для CI: если правка детекторов уронит полноту или добавит
ложных срабатываний, сборка упадёт. Полный замер — python -m bench.run."""

from bench.run import evaluate


def test_quality_does_not_regress(detector):
    report = evaluate(300, seed=7, detector=detector)
    total = sum(report.gold.values())
    assert sum(report.hidden.values()) / total >= 0.99, report.leaks
    assert report.false_masks == []
    for kind in ("PHONE", "EMAIL", "INN", "SNILS", "CARD", "PASSPORT", "ACCOUNT"):
        assert report.hidden[kind] == report.gold[kind], kind
