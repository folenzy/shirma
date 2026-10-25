"""Морфология имён: кто есть кто при разных падежах и в какой форме вернуть имя.

«Петру Иванову», «Пётр Иванов» и «Иванов» — один человек и одна метка [PER_1].
«Мария Иванова» — другой человек, хотя фамилия та же: другое имя.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

import pymorphy3

_ROLES = ("Name", "Surn", "Patr")
_INITIAL = re.compile(r"^[А-ЯЁ]\.$")


@lru_cache(maxsize=1)
def _analyzer() -> pymorphy3.MorphAnalyzer:
    return pymorphy3.MorphAnalyzer()


def _fold(word: str) -> str:
    return word.lower().replace("ё", "е")


@dataclass
class NameToken:
    surface: str
    role: str | None
    # Именительные формы, в которые может свестись слово: «Иванову» → {иванов, иванова}.
    forms: set[str]
    parses: list = field(default_factory=list, repr=False)

    def gender_options(self) -> set[str]:
        return {p.tag.gender for p in self.parses if p.tag.gender in ("masc", "femn")}


def _name_parses(word: str) -> list:
    parses = [p for p in _analyzer().parse(word) if any(r in p.tag for r in _ROLES)]
    # «Анне» в словаре есть и как несклоняемое имя; склоняемое чтение
    # у русских имён почти всегда вернее, поэтому оно идёт первым.
    return sorted(parses, key=lambda p: "Fixd" in p.tag)


def is_name_word(word: str, lenient: bool = False) -> bool:
    """Слово — имя, фамилия или отчество, и это его основное чтение.
    Нужна осторожность: «Звонил» тоже с большой буквы в начале фразы.
    lenient — достаточно любого «именного» чтения (рядом уже есть отчество)."""
    parses = _analyzer().parse(word)
    best = parses[0]
    if any(r in best.tag for r in _ROLES):
        return True
    if lenient and any(any(r in p.tag for r in ("Name", "Surn")) for p in parses):
        return True
    # Отчества и фамилии на -вич/-вна/-ов/-ин словарь иногда ставит вторым чтением.
    return best.tag.POS == "NOUN" and any(
        any(r in p.tag for r in _ROLES) and p.score >= 0.25 for p in parses[1:]
    )


_FUNCTION_POS = {
    "VERB",
    "INFN",
    "PRTF",
    "PRTS",
    "GRND",
    "ADVB",
    "CONJ",
    "PREP",
    "PRCL",
    "INTJ",
    "NPRO",
    "PRED",
}


def is_function_word(word: str) -> bool:
    parse = _analyzer().parse(word)[0]
    return parse.tag.POS in _FUNCTION_POS and not any(r in parse.tag for r in _ROLES)


_PROPER = ("Name", "Surn", "Patr", "Orgn", "Geox", "Trad", "Abbr")


def is_common_word(word: str) -> bool:
    """Словарное нарицательное слово: «Банк», «Перезвони». Неизвестные словарю
    названия («Сбербанк», «Ромашка» в кавычках) сюда не попадают."""
    parses = _analyzer().parse(word)
    return parses[0].is_known and not any(r in p.tag for p in parses for r in _PROPER)


def has_patronymic(text: str) -> bool:
    return any("Patr" in _analyzer().parse(w)[0].tag for w in text.split())


def _token(word: str) -> NameToken:
    if _INITIAL.match(word):
        return NameToken(word, "Init", {_fold(word)})
    parses = _name_parses(word)
    if not parses:
        return NameToken(word, None, {_fold(word)})
    forms = set()
    for p in parses:
        nomn = p.inflect({"nomn"})
        forms.add(_fold(nomn.word if nomn else p.word))
    role = next(r for r in _ROLES if r in parses[0].tag)
    return NameToken(word, role, forms, parses)


def _mention_gender(tokens: list[NameToken]) -> str | None:
    # Имя и отчество определяют род надёжно, фамилия — только если однозначна.
    for t in tokens:
        if t.role in ("Name", "Patr"):
            options = {p.tag.gender for p in t.parses[:1]}
            if options & {"masc", "femn"}:
                return options.pop()
    common: set[str] | None = None
    for t in tokens:
        if t.role == "Surn":
            common = t.gender_options() if common is None else common & t.gender_options()
    if common and len(common) == 1:
        return common.pop()
    return None


@dataclass
class Person:
    """Один человек: все упоминания и форма, в которой его вернуть."""

    tokens: list[NameToken]
    gender: str | None
    surfaces: list[str]

    @classmethod
    def from_text(cls, text: str) -> "Person":
        tokens = [_token(w) for w in text.split()]
        return cls(tokens, _mention_gender(tokens), [text])

    def _first_names(self) -> set[str]:
        return {f for t in self.tokens if t.role == "Name" for f in t.forms}

    def same_as(self, other: "Person") -> bool:
        if self.gender and other.gender and self.gender != other.gender:
            return False
        mine, theirs = self._first_names(), other._first_names()
        if mine and theirs and not mine & theirs:
            return False
        short, long_ = sorted((self, other), key=lambda p: len(p.tokens))
        pool = [t.forms for t in long_.tokens if t.role != "Init"]
        meaningful = [t for t in short.tokens if t.role != "Init"]
        return bool(meaningful) and all(any(t.forms & f for f in pool) for t in meaningful)

    def absorb(self, other: "Person") -> None:
        self.surfaces.append(other.surfaces[0])
        self.gender = self.gender or other.gender
        if len(other.tokens) > len(self.tokens):
            self.tokens = other.tokens

    def render(self, case: str = "nomn") -> str:
        words = [self._inflect(t, case) for t in self.tokens]
        return " ".join(words)

    def _inflect(self, token: NameToken, case: str) -> str:
        if not token.parses:
            return token.surface
        parses = token.parses
        if self.gender:
            parses = [p for p in parses if p.tag.gender == self.gender] or parses
        else:
            # Род неизвестен: считаем, что слово уже стоит в именительном
            # («Котова» — это она, а не «нет Котова»).
            parses = [p for p in parses if p.tag.case == "nomn"] or parses
        form = parses[0].inflect({case, "sing"})
        if form is None:
            return token.surface
        word = form.word
        return word[:1].upper() + word[1:] if token.surface[:1].isupper() else word


# Падеж по предлогу перед меткой. Глагольное управление («позвоните кому»)
# так не угадать — тогда остаётся именительный, это честный компромисс.
_PREPOSITION_CASE = {
    "у": "gent",
    "от": "gent",
    "для": "gent",
    "без": "gent",
    "до": "gent",
    "из": "gent",
    "около": "gent",
    "возле": "gent",
    "кроме": "gent",
    "после": "gent",
    "против": "gent",
    "к": "datv",
    "ко": "datv",
    "по": "datv",
    "благодаря": "datv",
    "с": "ablt",
    "со": "ablt",
    "над": "ablt",
    "под": "ablt",
    "перед": "ablt",
    "между": "ablt",
    "о": "loct",
    "об": "loct",
    "обо": "loct",
    "при": "loct",
    "про": "accs",
    "через": "accs",
    "за": "ablt",
}
_LAST_WORD = re.compile(r"([А-Яа-яЁё]+)\s*$")


def guess_case(before: str) -> str:
    m = _LAST_WORD.search(before[-40:])
    return _PREPOSITION_CASE.get(m.group(1).lower(), "nomn") if m else "nomn"
