from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .detect import Kind

DEFAULT_MASK = {
    Kind.PER, Kind.ORG, Kind.ADDRESS, Kind.PHONE, Kind.EMAIL,
    Kind.INN, Kind.SNILS, Kind.CARD, Kind.PASSPORT, Kind.ACCOUNT,
}  # fmt: skip

HINT = (
    "В сообщениях встречаются метки вида [PER_1], [PHONE_2] — ими скрыты данные. "
    "Пиши метки в ответе дословно, в квадратных скобках, не склоняй их и не "
    "пытайся угадать, что за ними стоит."
)


class Policy(BaseModel):
    # Что прятать. Города (LOC) по умолчанию открыты: «встреча в Москве» — не ПДн.
    mask: set[Kind] = Field(default_factory=lambda: set(DEFAULT_MASK))
    # Значения, которые прятать не нужно: название своей компании, публичные лица.
    allow: list[str] = Field(default_factory=list)
    # Склонять имя по предлогу при возврате: «для [PER_1]» → «для Петра Иванова».
    restore_case: bool = True
    # Добавлять системную подсказку, чтобы модель не портила метки.
    inject_hint: bool = True

    def allowed(self, value: str) -> bool:
        folded = value.casefold()
        return any(a.casefold() == folded for a in self.allow)

    @classmethod
    def load(cls, path: Path | None) -> "Policy":
        if path is None:
            return cls()
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
