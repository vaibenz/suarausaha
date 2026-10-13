import pytest

from suarausaha.parser import parse, tokenize, words_to_number


@pytest.mark.parametrize(
    "phrase, value",
    [
        ("lima ribu", 5000),
        ("lima belas ribu", 15000),
        ("dua puluh lima ribu", 25000),
        ("seratus lima puluh ribu", 150000),
        ("dua ribu lima ratus", 2500),
        ("seribu lima ratus", 1500),
        ("sebelas ribu", 11000),
        ("satu setengah juta", 1_500_000),
        ("15rb", 15000),
        ("15.000", 15000),
        ("1,5jt", 1_500_000),
        ("5k", 5000),
        ("3500", 3500),
    ],
)
def test_numbers(phrase, value):
    assert words_to_number(tokenize(phrase)) == value


def one(text):
    r = parse(text)
    assert not r.errors, r.errors
    assert len(r.actions) == 1
    return r.actions[0]


def test_simple_sale_with_number_words():
    a = one("jual tiga kopi lima ribu")
    assert (a.kind, a.item, a.quantity, a.unit_price, a.payment_method) == ("sale", "kopi", 3, 5000, "tunai")


def test_payment_method_and_multiword_item():
    a = one("laku 2 nasi goreng 15rb pakai qris")
    assert (a.item, a.quantity, a.unit_price, a.payment_method) == ("nasi goreng", 2, 15000, "qris")


def test_credit_sale_records_customer():
    a = one("bu sri ngutang dua indomie 3500")
    assert (a.payment_method, a.customer, a.item, a.quantity) == ("hutang", "Bu Sri", "indomie", 2)


def test_total_price_is_divided():
    a = one("jual 4 es teh total 20 ribu")
    assert a.unit_price == 5000 and a.quantity == 4


def test_measure_words_are_dropped():
    a = one("beli 2 karung beras 300 ribu")
    assert (a.kind, a.item, a.quantity, a.unit_price) == ("expense", "beras", 2, 300000)


def test_multiple_clauses_inherit_the_verb():
    r = parse("jual 2 kopi 5 ribu, 3 roti bakar 12 ribu dan beli gas 22 ribu")
    assert [(a.kind, a.item, a.quantity, a.unit_price) for a in r.actions] == [
        ("sale", "kopi", 2, 5000), ("sale", "roti bakar", 3, 12000), ("expense", "gas", 1, 22000)]


def test_missing_price_asks_instead_of_guessing():
    r = parse("jual 3 kopi")
    assert r.actions == [] and r.errors == ["Harga untuk kopi belum disebut."]


def test_unrelated_speech_is_an_error():
    r = parse("halo apa kabar")
    assert r.actions == [] and r.errors


@pytest.mark.parametrize("text, intent", [("rekap hari ini dong", "summary"), ("batalkan yang terakhir", "undo")])
def test_commands(text, intent):
    assert parse(text).intent == intent
