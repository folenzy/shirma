"""Синтетический корпус деловых сообщений с размеченными персональными данными.

Все данные выдуманы (Faker + сгенерированные номера с верными контрольными
суммами), поэтому корпус можно публиковать и гонять в CI. Имена ставятся
в нужный падеж по шаблону — проверяется именно работа со склонением.
"""

import random
import re
from dataclasses import dataclass

import pymorphy3
from faker import Faker

from shirma.detect import Kind

_morph = pymorphy3.MorphAnalyzer()

TEMPLATES = [
    "Коллеги, поручить {PER:datv} подготовить договор с {ORG} до пятницы. Контакт: {PHONE}.",
    "Прошу согласовать командировку {PER:gent}. Паспорт: серия {PASSPORT}, СНИЛС {SNILS}.",
    "Счёт на оплату от {ORG}, ИНН {INN}, р/с {ACCOUNT}. Сумма 125 400 руб., заказ № 4471.",
    "Звонил {PER:nomn}, просил перезвонить на {PHONE} или написать на {EMAIL}.",
    "Документы отправить курьером по адресу {ADDRESS}, получатель — {PER:nomn}.",
    "Встреча с {PER:ablt} перенесена на 14:00, переговорная 3, этаж 7.",
    "Возврат средств на карту {CARD}, держатель {PER:nomn}, обращение № 2024-118.",
    "По поручению {PER:gent} направляем сведения: ИНН {INN}, СНИЛС {SNILS}, тел. {PHONE}.",
    "Напомните {PER:datv}, что отчёт по проекту «Север» нужен к 15 ноября.",
    "Новый сотрудник: {PER:nomn}, {EMAIL}, адрес регистрации: {ADDRESS}.",
    "Письмо о {PER:loct} передано в отдел кадров. Ответ ждём в течение 10 дней.",
    "Перевести 50 000 руб. на счёт {ACCOUNT} в пользу {ORG}, назначение: оплата по договору 17/3.",
    "Клиент {PER:nomn} (паспорт {PASSPORT}) жалуется на списание с карты {CARD}.",
    "Согласовано с {PER:ablt} и {PER:ablt}. Итоги разошлём в Москве после совещания.",
    # Глагол в начале фразы с большой буквы — частая ложная «персона» у NER.
    "Подготовь ответ для {PER:gent} по претензии от {ORG}, срок — три рабочих дня.",
    "Перезвони {PER:datv} на {PHONE}, Банк одобрил заявку по проекту «Волга».",
]

# Падежи у шаблонов — для разбора меток вида {PER:datv}.
_SLOT = re.compile(r"\{(\w+)(?::(\w+))?\}")


@dataclass
class Gold:
    start: int
    stop: int
    kind: Kind
    text: str


@dataclass
class Sample:
    text: str
    gold: list[Gold]


def _inflect(word: str, case: str, gender: str) -> str:
    for p in _morph.parse(word):
        if any(r in p.tag for r in ("Name", "Surn", "Patr")) and p.tag.gender == gender:
            form = p.inflect({case, "sing"})
            if form:
                return form.word.capitalize()
    return word


class Generator:
    def __init__(self, seed: int = 42) -> None:
        self.rnd = random.Random(seed)
        self.fake = Faker("ru_RU")
        self.fake.seed_instance(seed)

    def person(self, case: str) -> str:
        f, rnd = self.fake, self.rnd
        gender = rnd.choice(["masc", "femn"])
        if gender == "masc":
            first, middle, last = f.first_name_male(), f.middle_name_male(), f.last_name_male()
        else:
            first, middle, last = (
                f.first_name_female(),
                f.middle_name_female(),
                f.last_name_female(),
            )
        layout = rnd.choice(
            [(first, last), (last, first, middle), (first, middle, last), (first, middle), (last,)]
        )
        return " ".join(_inflect(w, case, gender) for w in layout)

    def phone(self) -> str:
        d = "9" + "".join(str(self.rnd.randint(0, 9)) for _ in range(9))
        return self.rnd.choice(
            [
                f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}",
                f"8 {d[:3]} {d[3:6]}-{d[6:8]}-{d[8:]}",
                f"+7{d}",
                f"8-{d[:3]}-{d[3:6]}-{d[6:8]}-{d[8:]}",
            ]
        )

    def inn(self) -> str:
        if self.rnd.random() < 0.5:
            d = [self.rnd.randint(0, 9) for _ in range(9)]
            d.append(
                sum(a * b for a, b in zip(d, (2, 4, 10, 3, 5, 9, 4, 6, 8), strict=True)) % 11 % 10
            )
        else:
            d = [self.rnd.randint(0, 9) for _ in range(10)]
            d.append(
                sum(a * b for a, b in zip(d, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8), strict=True))
                % 11
                % 10
            )
            d.append(
                sum(a * b for a, b in zip(d, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), strict=True))
                % 11
                % 10
            )
        return "".join(map(str, d))

    def snils(self) -> str:
        d = [self.rnd.randint(0, 9) for _ in range(9)]
        d[0] = self.rnd.randint(1, 9)
        total = sum(n * w for n, w in zip(d, range(9, 0, -1), strict=True))
        total = total % 101 if total > 101 else total
        control = 0 if total in (100, 101) else total
        s = "".join(map(str, d))
        return self.rnd.choice([f"{s[:3]}-{s[3:6]}-{s[6:]} {control:02d}", f"{s}{control:02d}"])

    def card(self) -> str:
        d = [self.rnd.choice([2, 4, 5])] + [self.rnd.randint(0, 9) for _ in range(14)]
        total = 0
        for i, n in enumerate(reversed(d)):
            if i % 2 == 0:
                n = n * 2 - 9 if n * 2 > 9 else n * 2
            total += n
        d.append((10 - total % 10) % 10)
        s = "".join(map(str, d))
        return self.rnd.choice([s, " ".join(s[i : i + 4] for i in range(0, 16, 4))])

    def passport(self) -> str:
        r = self.rnd
        series = f"{r.randint(10, 99)} {r.randint(0, 99):02d}"
        number = f"{r.randint(0, 999999):06d}"
        return r.choice([f"{series} № {number}", f"{series.replace(' ', '')} {number}"])

    def account(self) -> str:
        return self.rnd.choice(["40817810", "40702810", "40802810"]) + "".join(
            str(self.rnd.randint(0, 9)) for _ in range(12)
        )

    def address(self) -> str:
        f, r = self.fake, self.rnd
        if r.random() < 0.5:
            return f.address().rsplit(",", 1)[0]  # без индекса в конце
        return f"г. {f.city_name()}, ул. {f.street_title()}, д. {r.randint(1, 120)}, кв. {r.randint(1, 300)}"

    def org(self) -> str:
        return self.rnd.choice(
            [
                f"ООО «{self.fake.word().capitalize()}»",
                f"АО «{self.fake.word().capitalize()}-{self.fake.word().capitalize()}»",
                f"ИП {self.fake.last_name()}",
            ]
        )

    def value(self, kind: str, case: str | None) -> str:
        match kind:
            case "PER":
                return self.person(case or "nomn")
            case "PHONE":
                return self.phone()
            case "EMAIL":
                return self.fake.free_email()
            case "INN":
                return self.inn()
            case "SNILS":
                return self.snils()
            case "CARD":
                return self.card()
            case "PASSPORT":
                return self.passport()
            case "ACCOUNT":
                return self.account()
            case "ADDRESS":
                return self.address()
            case "ORG":
                return self.org()
        raise ValueError(kind)

    def sample(self) -> Sample:
        template = self.rnd.choice(TEMPLATES)
        out, gold, pos = [], [], 0
        length = 0
        for m in _SLOT.finditer(template):
            literal = template[pos : m.start()]
            out.append(literal)
            length += len(literal)
            value = self.value(m.group(1), m.group(2))
            gold.append(Gold(length, length + len(value), Kind(m.group(1)), value))
            out.append(value)
            length += len(value)
            pos = m.end()
        out.append(template[pos:])
        return Sample("".join(out), gold)

    def corpus(self, n: int) -> list[Sample]:
        return [self.sample() for _ in range(n)]
