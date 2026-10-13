from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from suarausaha.api import create_app
from suarausaha.bookkeeper import GeminiBookkeeper, OfflineBookkeeper
from suarausaha.ledger import TZ, Ledger, rupiah


@pytest.fixture
def ledger():
    return Ledger(":memory:")


@pytest.fixture
def client(ledger):
    return TestClient(create_app(ledger, OfflineBookkeeper(ledger)))


def test_rupiah_format():
    assert rupiah(1500000) == "Rp1.500.000"


def test_text_entry_end_to_end(client):
    r = client.post("/api/entries/text", json={"text": "jual tiga kopi lima ribu"}).json()
    assert r["speech"] == "Tercatat penjualan 3 kopi, total Rp15.000."
    assert r["entries"][0]["amount"] == 15000
    assert client.get("/api/entries").json()[0]["item"] == "kopi"


def test_summary_counts_credit_separately(client):
    for text in ["jual 2 kopi 5 ribu", "bu sri ngutang dua indomie 3500", "beli gas 22 ribu"]:
        client.post("/api/entries/text", json={"text": text})
    s = client.get("/api/summary").json()
    assert s["sales_total"] == 17000
    assert s["cash_received"] == 10000
    assert s["credit_outstanding"] == 7000
    assert s["expenses_total"] == 22000
    assert s["profit_estimate"] == -5000
    spoken = client.post("/api/entries/text", json={"text": "rekap hari ini"}).json()["speech"]
    assert spoken.startswith("Hari ini penjualan Rp17.000") and "Hutang pelanggan Rp7.000" in spoken


def test_undo(client):
    client.post("/api/entries/text", json={"text": "jual 2 kopi 5 ribu"})
    r = client.post("/api/entries/text", json={"text": "batalkan yang terakhir"}).json()
    assert r["undone"]["item"] == "kopi"
    assert client.get("/api/entries").json() == []
    assert client.delete("/api/entries/last").status_code == 404


def test_errors_are_spoken_back(client):
    r = client.post("/api/entries/text", json={"text": "jual 3 kopi"}).json()
    assert r["entries"] == [] and r["speech"] == "Harga untuk kopi belum disebut."


def test_validation(client):
    assert client.post("/api/entries/text", json={"text": ""}).status_code == 422
    assert client.post("/api/entries/voice", files={"audio": ("a.txt", b"x", "text/plain")}).status_code == 415


def test_voice_without_gemini_is_503(client):
    r = client.post("/api/entries/voice", files={"audio": ("a.webm", b"\x1a\x45", "audio/webm")})
    assert r.status_code == 503
    assert client.get("/api/health").json() == {"status": "ok", "engine": "offline", "audio": False}


def test_entries_filtered_by_day(ledger):
    ledger.add("sale", "kopi", 1, 5000, when=datetime(2026, 1, 5, 9, tzinfo=TZ))
    ledger.add("sale", "teh", 1, 4000, when=datetime(2026, 1, 6, 9, tzinfo=TZ))
    client = TestClient(create_app(ledger, OfflineBookkeeper(ledger)))
    assert [e["item"] for e in client.get("/api/entries", params={"day": "2026-01-05"}).json()] == ["kopi"]
    assert client.get("/api/summary", params={"day": "2026-01-06"}).json()["sales_total"] == 4000


def test_gemini_function_calls_are_executed_and_validated(ledger, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    bk = GeminiBookkeeper(ledger)
    calls = [
        SimpleNamespace(name="record_sale", args={"item": "nasi goreng", "quantity": 2, "unit_price": 15000,
                                                  "payment_method": "qris"}),
        SimpleNamespace(name="record_expense", args={"item": "gas", "quantity": 1, "unit_price": 22000}),
        SimpleNamespace(name="record_sale", args={"item": "kopi", "quantity": -1, "unit_price": 5000}),
    ]
    seen = {}

    def fake_generate(model, contents, config):
        seen["config"] = config
        return SimpleNamespace(function_calls=calls, text=None)

    monkeypatch.setattr(bk.client.models, "generate_content", fake_generate)
    out = bk.process_text("laku dua nasi goreng 15rb pakai qris, beli gas 22rb, jual kopi")
    assert [e.item for e in out.entries] == ["nasi goreng", "gas"]
    assert out.messages[0] == "Tercatat penjualan 2 nasi goreng, total Rp30.000, lewat QRIS."
    assert len(out.errors) == 1  # the negative quantity was rejected by the ledger, not written
    names = [f.name for f in seen["config"].tools[0].function_declarations]
    assert names == ["record_sale", "record_expense", "get_daily_summary", "undo_last_entry"]


def test_gemini_text_reply_without_calls_becomes_a_question(ledger, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    bk = GeminiBookkeeper(ledger)
    monkeypatch.setattr(bk.client.models, "generate_content",
                        lambda **kw: SimpleNamespace(function_calls=None, text="Harganya berapa?"))
    out = bk.process_text("jual tiga kopi")
    assert out.entries == [] and out.speech == "Harganya berapa?"
