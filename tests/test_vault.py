from shirma.detect import Detector
from shirma.morph import guess_case
from shirma.policy import Policy
from shirma.vault import Vault


def test_same_person_in_different_cases_gets_one_placeholder(vault):
    masked, _ = vault.mask("Поручить Петру Иванову. Иванов обещал. Пётр Иванов согласен.")
    assert masked == "Поручить [PER_1]. [PER_1] обещал. [PER_1] согласен."


def test_same_surname_different_first_name_is_another_person(vault):
    masked, _ = vault.mask("Пётр Иванов и Мария Иванова пришли вместе.")
    assert masked == "[PER_1] и [PER_2] пришли вместе."


def test_same_value_same_placeholder_across_formats(vault):
    masked, _ = vault.mask("Звоните +7 916 123-45-67 или 8(916)1234567.")
    assert masked == "Звоните [PHONE_1] или [PHONE_1]."


def test_placeholders_are_stable_across_messages(vault):
    first, _ = vault.mask("Пишите Анне Котовой.")
    second, _ = vault.mask("Котова ответила.")
    assert first == "Пишите [PER_1]."
    assert second == "[PER_1] ответила."


def test_restore_inflects_by_preposition(vault):
    vault.mask("Поручить Петру Иванову.")
    assert vault.restore("Задача для [PER_1].") == "Задача для Петра Иванова."
    assert vault.restore("Созвонюсь с [PER_1].") == "Созвонюсь с Петром Ивановым."
    assert vault.restore("[PER_1] сделает.") == "Пётр Иванов сделает."


def test_restore_keeps_feminine_surname(vault):
    vault.mask("Отправьте Анне Сергеевне Котовой.")
    assert vault.restore("Письмо для [PER_1].") == "Письмо для Анны Сергеевны Котовой."


def test_restore_without_case_policy(detector: Detector):
    vault = Vault(detector, Policy(restore_case=False))
    vault.mask("Поручить Петру Иванову.")
    assert vault.restore("Задача для [PER_1].") == "Задача для Пётр Иванов."


def test_unknown_placeholder_left_as_is(vault):
    vault.mask("Звоните +7 916 123-45-67.")
    assert vault.restore("[PHONE_1] и [PHONE_7]") == "+7 916 123-45-67 и [PHONE_7]"


def test_allow_list(detector: Detector):
    vault = Vault(detector, Policy(allow=["ООО «Ромашка»"]))
    masked, _ = vault.mask("Договор с ООО «Ромашка» подписан.")
    assert masked == "Договор с ООО «Ромашка» подписан."


def test_guess_case():
    assert guess_case("письмо для ") == "gent"
    assert guess_case("вместе с ") == "ablt"
    assert guess_case("подойти к") == "datv"
    assert guess_case("Ответственный — ") == "nomn"
    assert guess_case("") == "nomn"
