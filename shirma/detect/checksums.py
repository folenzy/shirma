"""Контрольные суммы российских идентификаторов и номеров карт.

Регулярное выражение находит «похожее на ИНН», а контрольная сумма отсекает
случайные числа той же длины: номера заказов, артикулы, суммы в копейках.
"""


def _digits(value: str) -> list[int]:
    return [int(c) for c in value if c.isdigit()]


def _inn_check(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def inn_valid(value: str) -> bool:
    """ИНН юрлица (10 цифр) или физлица (12 цифр)."""
    d = _digits(value)
    if len(d) == 10:
        return _inn_check(d, (2, 4, 10, 3, 5, 9, 4, 6, 8)) == d[9]
    if len(d) == 12:
        c11 = _inn_check(d, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
        c12 = _inn_check(d, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
        return c11 == d[10] and c12 == d[11]
    return False


def snils_valid(value: str) -> bool:
    d = _digits(value)
    if len(d) != 11:
        return False
    number, control = d[:9], d[9] * 10 + d[10]
    # Номера до 001-001-998 выдавались без контроля, их не встретить в живых данных.
    if int("".join(map(str, number))) <= 1001998:
        return False
    total = sum(n * w for n, w in zip(number, range(9, 0, -1), strict=True))
    if total > 101:
        total %= 101
    expected = 0 if total in (100, 101) else total
    return expected == control


def luhn_valid(value: str) -> bool:
    d = _digits(value)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(d)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
