"""Rule based parser for spoken Bahasa Indonesia bookkeeping phrases.

This is the offline path and the safety net when Gemini is unavailable. It turns
phrases like these into ledger actions:

    "jual tiga kopi lima ribu"                 sale, 3 x kopi at Rp5.000
    "laku 2 nasi goreng 15rb pakai qris"       sale paid by QRIS
    "bu sri ngutang dua indomie 3500"          credit sale to Bu Sri
    "beli gas 22 ribu dan bayar listrik 150rb" two expenses
    "jual 4 es teh total 20 ribu"              total price, so Rp5.000 each

A price after the item is read as a unit price unless the phrase says total,
jadi or semuanya.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DIGITS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7, "delapan": 8,
          "sembilan": 9, "nol": 0}
SPECIAL = {"sepuluh": 10, "sebelas": 11, "seratus": 100, "seribu": 1000, "sejuta": 1_000_000, "setengah": 0.5}
MULTIPLIERS = {"belas", "puluh", "ratus", "ribu", "rb", "k", "juta", "jt"}
NUMBER_WORDS = set(DIGITS) | set(SPECIAL) | MULTIPLIERS

SALE_VERBS = {"jual", "menjual", "laku", "terjual", "laris", "dijual"}
EXPENSE_VERBS = {"beli", "membeli", "bayar", "membayar", "belanja", "keluar", "ongkos", "biaya"}
CREDIT_VERBS = {"hutang", "utang", "ngutang", "ngebon", "kasbon", "bon"}
HONORIFICS = {"bu", "ibu", "pak", "bapak", "mas", "mbak", "kak", "bang"}
MEASURES = {"buah", "biji", "bungkus", "gelas", "porsi", "botol", "karung", "kilo", "kg", "liter", "pack",
            "dus", "sachet", "batang", "piring", "mangkok", "ekor", "lembar", "pcs", "x"}
FILLER = {"tadi", "saya", "aku", "sudah", "udah", "yang", "ke", "untuk", "buat", "harga", "harganya", "rp",
          "rupiah", "per", "@", "masing", "masing2", "satunya", "pakai", "pake", "lewat", "via", "dengan",
          "sama", "itu", "ini", "lagi", "juga", "ya", "nih", "dong", "total", "jadi", "semuanya", "semua", "seharga"}
PAYMENT = {"qris": "qris", "transfer": "transfer", "tf": "transfer", "tunai": "tunai", "cash": "tunai"}
TOTAL_WORDS = {"total", "jadi", "semuanya", "semua"}
CLAUSE_SPLIT = re.compile(r"\s*(?:,|;|\bdan\b|\bterus\b|\blalu\b|\bkemudian\b)\s*")


@dataclass
class Action:
    kind: str  # sale or expense
    item: str
    quantity: float
    unit_price: int
    payment_method: str = "tunai"
    customer: str | None = None

    def to_tool_call(self) -> dict:
        name = "record_sale" if self.kind == "sale" else "record_expense"
        args = {"item": self.item, "quantity": self.quantity, "unit_price": self.unit_price}
        if self.kind == "sale":
            args["payment_method"] = self.payment_method
            if self.customer:
                args["customer"] = self.customer
        return {"name": name, "args": args}


@dataclass
class ParseResult:
    actions: list[Action] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    intent: str | None = None  # "summary" or "undo" for non ledger commands


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("rp.", " ").replace("rp", " rp ")
    # "15.000" and "15,000" are thousands; "1,5" is a decimal
    text = re.sub(r"(\d)[.,](\d{3})\b", r"\1\2", text)
    text = re.sub(r"(\d)[.,](\d{3})\b", r"\1\2", text)
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    # split glued suffixes: 15rb, 5k, 1.5jt, 2x
    text = re.sub(r"(\d)(rb|ribu|k|jt|juta|x)\b", r"\1 \2", text)
    text = text.replace("@", " @ ")
    return re.findall(r"[a-z]+\d*|\d+(?:\.\d+)?|@", text)


def is_number_token(tok: str) -> bool:
    return tok in NUMBER_WORDS or bool(re.fullmatch(r"\d+(?:\.\d+)?", tok))


def words_to_number(tokens: list[str]) -> float:
    """Converts number words and digits to a value: "seratus lima puluh ribu" is 150000."""
    total, group, last = 0.0, 0.0, 0.0
    for tok in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            group, last = group + last, float(tok)
        elif tok in DIGITS:
            group, last = group + last, DIGITS[tok]
        elif tok == "setengah":
            group, last = group + last + 0.5, 0
        elif tok in ("seribu", "sejuta"):
            total += SPECIAL[tok]
        elif tok in SPECIAL:
            group, last = group + last + SPECIAL[tok], 0
        elif tok == "belas":
            group, last = group + last + 10, 0
        elif tok == "puluh":
            group, last = group + last * 10, 0
        elif tok == "ratus":
            group, last = group + (last or 1) * 100, 0
        elif tok in ("ribu", "rb", "k"):
            total += ((group + last) or 1) * 1000
            group, last = 0, 0
        elif tok in ("juta", "jt"):
            total += ((group + last) or 1) * 1_000_000
            group, last = 0, 0
    return total + group + last


def number_spans(tokens: list[str]) -> list[tuple[int, int, float]]:
    """Returns (start, end, value) for each maximal run of number tokens."""
    spans, i = [], 0
    while i < len(tokens):
        if is_number_token(tokens[i]) and tokens[i] not in MULTIPLIERS:
            j = i
            while j < len(tokens) and is_number_token(tokens[j]):
                # a new bare number after a finished amount starts a new span: "2 5000"
                if j > i and re.fullmatch(r"\d+(?:\.\d+)?", tokens[j]) and tokens[j - 1] not in DIGITS:
                    break
                j += 1
            spans.append((i, j, words_to_number(tokens[i:j])))
            i = j
        else:
            i += 1
    return spans


def parse(text: str) -> ParseResult:
    lowered = text.lower()
    if re.search(r"\b(rekap|ringkasan|total hari ini|untung hari ini|berapa untung|laporan)\b", lowered):
        return ParseResult(intent="summary")
    if re.search(r"\b(batal|batalkan|hapus|salah catat|undo)\b", lowered):
        return ParseResult(intent="undo")

    result = ParseResult()
    kind: str | None = None
    payment = "tunai"
    customer: str | None = None
    for p_word, method in PAYMENT.items():
        if re.search(rf"\b{p_word}\b", lowered):
            payment = method

    for clause in [c for c in CLAUSE_SPLIT.split(lowered) if c.strip()]:
        tokens = tokenize(clause)
        if not tokens:
            continue
        if any(t in CREDIT_VERBS for t in tokens):
            kind, payment = "sale", "hutang"
        elif any(t in SALE_VERBS for t in tokens):
            kind = "sale"
        elif any(t in EXPENSE_VERBS for t in tokens):
            kind = "expense"
        if kind is None:
            result.errors.append(f"Tidak jelas apakah '{clause.strip()}' penjualan atau pengeluaran.")
            continue

        for i, t in enumerate(tokens[:-1]):
            if t in HONORIFICS and not is_number_token(tokens[i + 1]):
                customer = f"{t.capitalize()} {tokens[i + 1].capitalize()}"
        customer_words = set(customer.lower().split()) if customer else set()

        spans = number_spans(tokens)
        in_span = {k for s, e, _ in spans for k in range(s, e)}
        item_words = [t for k, t in enumerate(tokens) if k not in in_span and t not in SALE_VERBS | EXPENSE_VERBS
                      | CREDIT_VERBS | MEASURES | FILLER | set(PAYMENT) | customer_words and t != "@"]
        item = " ".join(item_words).strip()
        if not item:
            result.errors.append(f"Barangnya apa untuk '{clause.strip()}'?")
            continue

        quantity, price = 1.0, None
        if len(spans) >= 2:
            quantity, price = spans[0][2], spans[-1][2]
        elif len(spans) == 1:
            value = spans[0][2]
            if value >= 100:
                price = value
            else:
                quantity = value
        if price is None:
            result.errors.append(f"Harga untuk {item} belum disebut.")
            continue
        if any(t in TOTAL_WORDS for t in tokens) and quantity > 0:
            price = price / quantity

        result.actions.append(Action(kind=kind, item=item, quantity=quantity, unit_price=round(price),
                                     payment_method=payment if kind == "sale" else "tunai",
                                     customer=customer if kind == "sale" and payment == "hutang" else None))
    return result
