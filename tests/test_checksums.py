import pytest

from shirma.detect.checksums import inn_valid, luhn_valid, snils_valid


@pytest.mark.parametrize("value", ["7707083893", "500100732259", "7830002293"])
def test_inn_valid(value):
    assert inn_valid(value)


@pytest.mark.parametrize("value", ["7707083894", "500100732258", "1234567890", "123"])
def test_inn_invalid(value):
    assert not inn_valid(value)


@pytest.mark.parametrize("value", ["112-233-445 95", "11223344595", "087-654-303 00"])
def test_snils_valid(value):
    assert snils_valid(value)


@pytest.mark.parametrize("value", ["112-233-445 96", "000-000-111 00", "1234"])
def test_snils_invalid(value):
    assert not snils_valid(value)


def test_luhn():
    assert luhn_valid("4111 1111 1111 1111")
    assert luhn_valid("2200-0000-0000-0004")
    assert not luhn_valid("4111 1111 1111 1112")
    assert not luhn_valid("411111")
