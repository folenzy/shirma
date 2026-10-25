"""Детекторы по шаблонам: всё, у чего есть формат, а лучше — контрольная сумма."""

import re
from collections.abc import Callable, Iterator

from .checksums import inn_valid, luhn_valid, snils_valid
from .spans import Kind, Span

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.(?:[A-Za-z]{2,}|рф)(?![\w-])")

_PHONE = re.compile(r"(?<![\d\w])(?:\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")

_INN = re.compile(r"(?<![\d+])(?:\d{12}|\d{10})(?!\d)")

_SNILS = re.compile(r"(?<![\d+])(?:\d{3}-\d{3}-\d{3}[\s-]\d{2}|\d{11})(?!\d)")

_CARD = re.compile(r"(?<![\d+])(?:\d{4}[ -]){3}\d{4}(?:\d{3})?(?!\d)|(?<![\d+])\d{13,19}(?!\d)")

# Расчётные, лицевые и корреспондентские счета начинаются с 3 или 4.
_ACCOUNT = re.compile(r"(?<!\d)[34]\d{19}(?!\d)|(?<!\d)[34]\d{3}(?: \d{4}){4}(?!\d)")

# У паспорта нет контрольной суммы, поэтому без слова-якоря его не ищем:
# «4506 123456» без контекста — это что угодно.
_PASSPORT = re.compile(
    r"(?i)(?:паспорт\w*[^\d\n]{0,40}?|сери[яи]\s*)"
    r"(?P<num>\d{2}\s?\d{2}[^\d\n]{0,15}?\d{6})(?!\d)"
)

_SETTLEMENT = (
    r"(?:г\.|город|с\.|село|пос\.|п\.|пгт\.?|рп\.?|д\.|деревня|ст\.|ст-ца|станица"
    r"|к\.|клх|х\.|хутор|аул|снт)"
)
_REGION_NOTE = r"(?:\s\([А-ЯЁ][а-яё]+\.?\))?"  # «г. Ревда (Сверд.)»
_STREET_PRE = (
    r"(?:ул(?:ица|\.)|пр-к?т\.?|просп(?:ект|\.)|пр\.|пер(?:еулок|\.)|ш(?:оссе|\.)"
    r"|бул(?:ьвар|\.)|б-р|наб(?:ережная|\.)|пл(?:ощадь|\.)|проезд|пр-д|туп(?:ик|\.)"
    r"|алл(?:ея|\.)|мкр(?:н|\.)?\.?|микрорайон)"
)
_STREET_POST = r"(?:улица|ул\.|проспект|пр-т|бульвар|переулок|шоссе|проезд|набережная|площадь)"
_WORD = r"[\wЁё][\wЁё.\-]*"
_CAP_WORD = r"[А-ЯЁ][\wЁё\-]*"
_HOUSE = (
    r"(?:д(?:ом|\.)\s*)?\d+[а-яА-Я]?(?:/\d+)?"
    r"(?:\s*,?\s*(?:к(?:орп(?:ус)?)?\.?|стр(?:оение|\.)?|кв(?:артира|\.)?|оф(?:ис|\.)?)\s*\d+[а-я]?(?:/\d+)?)*"
)
_ADDRESS = re.compile(
    rf"(?:\d{{6}},?\s*)?"
    rf"(?:(?<![\wЁё]){_SETTLEMENT}\s*{_CAP_WORD}(?:\s{_CAP_WORD})?{_REGION_NOTE},?\s*)?"
    rf"(?:{_STREET_PRE}\s*{_WORD}(?:\s+{_WORD}){{0,3}}?|{_CAP_WORD}(?:\s{_CAP_WORD})?\s+{_STREET_POST})"
    rf",?\s*{_HOUSE}"
    rf"(?:,\s*\d{{6}})?(?!\d)"
)


def _plain(pattern: re.Pattern[str], kind: Kind, check: Callable[[str], bool] | None = None):
    def run(text: str) -> Iterator[Span]:
        for m in pattern.finditer(text):
            if check is None or check(m.group()):
                yield Span(m.start(), m.end(), kind, m.group())

    return run


def _passport(text: str) -> Iterator[Span]:
    for m in _PASSPORT.finditer(text):
        yield Span(m.start("num"), m.end("num"), Kind.PASSPORT, m.group("num"))


def _address(text: str) -> Iterator[Span]:
    for m in _ADDRESS.finditer(text):
        value = m.group().rstrip(" ,")
        yield Span(m.start(), m.start() + len(value), Kind.ADDRESS, value)


DETECTORS: dict[Kind, Callable[[str], Iterator[Span]]] = {
    Kind.EMAIL: _plain(_EMAIL, Kind.EMAIL),
    Kind.PHONE: _plain(_PHONE, Kind.PHONE),
    Kind.INN: _plain(_INN, Kind.INN, inn_valid),
    Kind.SNILS: _plain(_SNILS, Kind.SNILS, snils_valid),
    Kind.CARD: _plain(_CARD, Kind.CARD, luhn_valid),
    Kind.ACCOUNT: _plain(_ACCOUNT, Kind.ACCOUNT),
    Kind.PASSPORT: _passport,
    Kind.ADDRESS: _address,
}


def find_patterns(text: str, kinds: set[Kind]) -> list[Span]:
    return [span for kind in kinds if kind in DETECTORS for span in DETECTORS[kind](text)]
