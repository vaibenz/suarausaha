"""Turns a spoken or typed phrase into ledger entries.

GeminiBookkeeper sends the phrase (or the raw audio) to Gemini with four
declared functions and executes the calls it returns. Confirmations are built
from templates rather than taken from the model, so what the user hears always
matches what was written to the ledger.

OfflineBookkeeper uses the rule based parser and needs no network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .ledger import Entry, Ledger, rupiah, summary_sentence
from .parser import parse

SYSTEM_INSTRUCTION = """Kamu adalah asisten pembukuan untuk warung dan usaha mikro di Indonesia.
Pengguna berbicara bahasa Indonesia sehari hari, kadang dengan bahasa daerah atau singkatan.
Ubah ucapan mereka menjadi panggilan fungsi:
- record_sale untuk penjualan. Jika pelanggan berhutang (ngutang, ngebon, kasbon), payment_method = hutang dan isi customer.
- record_expense untuk pembelian stok, bayar listrik, gas, sewa dan pengeluaran lain.
- get_daily_summary jika pengguna minta rekap atau untung hari ini.
- undo_last_entry jika pengguna minta batalkan atau hapus catatan terakhir.
Harga dalam rupiah sebagai bilangan bulat. "lima ribu" = 5000, "15rb" = 15000, "1,5 juta" = 1500000.
Harga setelah nama barang adalah harga satuan, kecuali pengguna bilang total, jadi, atau semuanya.
Satu ucapan bisa berisi beberapa transaksi; panggil fungsi untuk masing masing.
Jangan menebak harga. Jika harga tidak disebut, jangan panggil fungsi dan tanyakan harganya."""


@dataclass
class Outcome:
    entries: list[Entry] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: dict | None = None
    undone: Entry | None = None
    engine: str = "offline"

    @property
    def speech(self) -> str:
        """Everything the screen reader and text to speech should say, in order."""
        return " ".join(self.messages + self.errors)

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "messages": self.messages,
            "errors": self.errors,
            "summary": self.summary,
            "undone": self.undone.to_dict() if self.undone else None,
            "speech": self.speech,
            "engine": self.engine,
        }


def confirm(entry: Entry) -> str:
    qty = int(entry.quantity) if float(entry.quantity).is_integer() else entry.quantity
    if entry.kind == "sale":
        text = f"Tercatat penjualan {qty} {entry.item}, total {rupiah(entry.amount)}"
        if entry.payment_method == "hutang":
            text += f", hutang {entry.customer}" if entry.customer else ", sebagai hutang"
        elif entry.payment_method != "tunai":
            text += f", lewat {entry.payment_method.upper() if entry.payment_method == 'qris' else entry.payment_method}"
        return text + "."
    return f"Tercatat pengeluaran {entry.item}, total {rupiah(entry.amount)}."


class ToolExecutor:
    """Executes the four bookkeeping functions against the ledger. Shared by both engines."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def run(self, name: str, args: dict, outcome: Outcome, source_text: str | None) -> None:
        try:
            if name == "record_sale":
                entry = self.ledger.add("sale", str(args["item"]), float(args.get("quantity", 1)),
                                        int(args["unit_price"]), str(args.get("payment_method", "tunai")),
                                        args.get("customer") or None, source_text)
                outcome.entries.append(entry)
                outcome.messages.append(confirm(entry))
            elif name == "record_expense":
                entry = self.ledger.add("expense", str(args["item"]), float(args.get("quantity", 1)),
                                        int(args["unit_price"]), "tunai", None, source_text)
                outcome.entries.append(entry)
                outcome.messages.append(confirm(entry))
            elif name == "get_daily_summary":
                outcome.summary = self.ledger.summary()
                outcome.messages.append(summary_sentence(outcome.summary))
            elif name == "undo_last_entry":
                outcome.undone = self.ledger.undo_last()
                outcome.messages.append(
                    f"Catatan terakhir dihapus: {outcome.undone.item}." if outcome.undone else "Belum ada catatan.")
            else:
                outcome.errors.append(f"Perintah tidak dikenal: {name}.")
        except (KeyError, ValueError, TypeError) as exc:
            outcome.errors.append(f"Tidak bisa dicatat ({exc}).")


class OfflineBookkeeper:
    engine = "offline"

    def __init__(self, ledger: Ledger):
        self.tools = ToolExecutor(ledger)

    def process_text(self, text: str) -> Outcome:
        outcome = Outcome(engine=self.engine)
        parsed = parse(text)
        if parsed.intent == "summary":
            self.tools.run("get_daily_summary", {}, outcome, text)
        elif parsed.intent == "undo":
            self.tools.run("undo_last_entry", {}, outcome, text)
        for action in parsed.actions:
            call = action.to_tool_call()
            self.tools.run(call["name"], call["args"], outcome, text)
        outcome.errors.extend(parsed.errors)
        if not outcome.messages and not outcome.errors:
            outcome.errors.append("Maaf, belum mengerti. Coba ucapkan misalnya: jual tiga kopi lima ribu.")
        return outcome

    def process_audio(self, audio: bytes, mime_type: str) -> Outcome:
        raise NotImplementedError("Audio needs Gemini. Use the browser's speech recognition and send text instead.")


def _function_declarations():
    from google.genai import types

    s = types.Schema
    T = types.Type
    return [
        types.FunctionDeclaration(
            name="record_sale",
            description="Catat penjualan barang atau jasa.",
            parameters=s(type=T.OBJECT, required=["item", "quantity", "unit_price"], properties={
                "item": s(type=T.STRING, description="Nama barang, huruf kecil, tanpa jumlah"),
                "quantity": s(type=T.NUMBER, description="Jumlah barang"),
                "unit_price": s(type=T.INTEGER, description="Harga satuan dalam rupiah"),
                "payment_method": s(type=T.STRING, enum=["tunai", "qris", "transfer", "hutang"]),
                "customer": s(type=T.STRING, description="Nama pelanggan jika berhutang, misalnya Bu Sri"),
            }),
        ),
        types.FunctionDeclaration(
            name="record_expense",
            description="Catat pengeluaran usaha seperti belanja stok, listrik, gas atau sewa.",
            parameters=s(type=T.OBJECT, required=["item", "quantity", "unit_price"], properties={
                "item": s(type=T.STRING, description="Nama pengeluaran, huruf kecil"),
                "quantity": s(type=T.NUMBER),
                "unit_price": s(type=T.INTEGER, description="Harga satuan dalam rupiah"),
            }),
        ),
        types.FunctionDeclaration(name="get_daily_summary", description="Rekap penjualan dan pengeluaran hari ini."),
        types.FunctionDeclaration(name="undo_last_entry", description="Hapus catatan terakhir karena salah."),
    ]


class GeminiBookkeeper:
    engine = "gemini"

    def __init__(self, ledger: Ledger, model: str | None = None):
        from google import genai
        from google.genai import types

        self.client = genai.Client()
        self.model = model or os.environ.get("SUARAUSAHA_MODEL", "gemini-2.5-flash")
        self.tools = ToolExecutor(ledger)
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,
            tools=[types.Tool(function_declarations=_function_declarations())],
            # We run the functions ourselves so every write goes through validation.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO")),
        )

    def _run(self, contents, source_text: str | None) -> Outcome:
        response = self.client.models.generate_content(model=self.model, contents=contents, config=self.config)
        outcome = Outcome(engine=self.engine)
        calls = response.function_calls or []
        for call in calls:
            self.tools.run(call.name, dict(call.args or {}), outcome, source_text)
        if not calls:
            outcome.errors.append((response.text or "Maaf, belum mengerti.").strip())
        return outcome

    def process_text(self, text: str) -> Outcome:
        return self._run(text, text)

    def process_audio(self, audio: bytes, mime_type: str) -> Outcome:
        from google.genai import types

        return self._run([types.Part.from_bytes(data=audio, mime_type=mime_type),
                          "Catat transaksi dari rekaman suara ini."], "(rekaman suara)")


def make_bookkeeper(ledger: Ledger):
    has_creds = bool(os.environ.get("GOOGLE_API_KEY")) or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    if os.environ.get("SUARAUSAHA_ENGINE") == "offline" or not has_creds:
        return OfflineBookkeeper(ledger)
    return GeminiBookkeeper(ledger)
