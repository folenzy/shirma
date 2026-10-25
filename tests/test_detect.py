import pytest

from shirma.detect import Kind
from shirma.policy import DEFAULT_MASK


def kinds(detector, text):
    return [(s.kind, s.text) for s in detector.find(text, DEFAULT_MASK)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("звоните +7 (916) 123-45-67", (Kind.PHONE, "+7 (916) 123-45-67")),
        ("тел. 8-916-123-45-67, спросить", (Kind.PHONE, "8-916-123-45-67")),
        ("пишите на ivan.p@yandex.ru.", (Kind.EMAIL, "ivan.p@yandex.ru")),
        ("почта: info@пример.рф", (Kind.EMAIL, "info@пример.рф")),
        ("ИНН 7707083893", (Kind.INN, "7707083893")),
        ("ИНН физлица 500100732259", (Kind.INN, "500100732259")),
        ("СНИЛС 112-233-445 95", (Kind.SNILS, "112-233-445 95")),
        ("карта 4111 1111 1111 1111", (Kind.CARD, "4111 1111 1111 1111")),
        ("паспорт: серия 45 06 № 123456", (Kind.PASSPORT, "45 06 № 123456")),
        ("паспорт 4506 123456 выдан", (Kind.PASSPORT, "4506 123456")),
        ("р/с 40817810099910004312", (Kind.ACCOUNT, "40817810099910004312")),
        (
            "адрес: г. Москва, ул. Ленина, д. 5, кв. 12.",
            (Kind.ADDRESS, "г. Москва, ул. Ленина, д. 5, кв. 12"),
        ),
        ("на Ленинский проспект, д. 12", (Kind.ADDRESS, "Ленинский проспект, д. 12")),
        ("ш. 50 лет ВЛКСМ, д. 3/6 стр. 2", (Kind.ADDRESS, "ш. 50 лет ВЛКСМ, д. 3/6 стр. 2")),
    ],
)
def test_patterns(detector, text, expected):
    assert expected in kinds(detector, text)


@pytest.mark.parametrize(
    "text",
    [
        "Номер заказа 1234567890, артикул 4111111111111112.",  # не проходят контрольные суммы
        "Сумма 12500 рублей, срок 30 дней, в 2026 году.",
        "Серия 4506 вышла в 2024 году.",  # без «№»/номера — не паспорт
    ],
)
def test_no_false_positives(detector, text):
    assert kinds(detector, text) == []


def test_names_merged_and_typed(detector):
    found = kinds(detector, "Согласовать с Анной Сергеевной Котовой из ООО «Ромашка».")
    assert (Kind.PER, "Анной Сергеевной Котовой") in found
    assert (Kind.ORG, "ООО «Ромашка»") in found


def test_verb_glued_to_name_is_trimmed(detector):
    assert kinds(detector, "Напомните Лыткиной Лидии Вадимовне про отчёт.") == [
        (Kind.PER, "Лыткиной Лидии Вадимовне")
    ]


def test_imperative_at_sentence_start_is_not_a_name(detector):
    found = kinds(detector, "Подготовь письмо для Анны Котовой.")
    assert found == [(Kind.PER, "Анны Котовой")]


def test_capitalized_common_noun_is_not_an_org(detector):
    assert kinds(detector, "Перезвони клиенту, Банк одобрил заявку.") == []


def test_surname_mistaken_for_place_is_a_person(detector):
    found = kinds(detector, "Согласовано с Фомичёвым и Меркушевым Арефием Фадеевичем.")
    assert (Kind.PER, "Фомичёвым") in found


def test_cities_are_not_masked_by_default(detector):
    assert kinds(detector, "Встреча пройдёт в Казани.") == []
