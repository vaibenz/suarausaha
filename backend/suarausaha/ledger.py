"""The shop ledger: sales, expenses and credit (hutang) in SQLite.

Amounts are whole rupiah integers. Rupiah has no minor unit in daily use, and
integers avoid floating point rounding in totals.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jakarta")
PAYMENT_METHODS = {"tunai", "qris", "transfer", "hutang"}
KINDS = {"sale", "expense"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('sale', 'expense')),
    item TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    payment_method TEXT NOT NULL,
    customer TEXT,
    source_text TEXT,
    created_at TEXT NOT NULL,
    day TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS entries_day ON entries (day);
"""


@dataclass
class Entry:
    id: int
    kind: str
    item: str
    quantity: float
    unit_price: int
    amount: int
    payment_method: str
    customer: str | None
    source_text: str | None
    created_at: str
    day: str

    def to_dict(self) -> dict:
        return asdict(self)


def rupiah(amount: int) -> str:
    """Formats 15000 as Rp15.000, the Indonesian convention."""
    return "Rp" + f"{amount:,}".replace(",", ".")


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def add(self, kind: str, item: str, quantity: float, unit_price: int, payment_method: str = "tunai",
            customer: str | None = None, source_text: str | None = None, when: datetime | None = None) -> Entry:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {sorted(KINDS)}")
        if payment_method not in PAYMENT_METHODS:
            payment_method = "tunai"
        if quantity <= 0 or unit_price < 0:
            raise ValueError("quantity must be positive and unit price must not be negative")
        when = when or datetime.now(TZ)
        amount = round(quantity * unit_price)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO entries (kind, item, quantity, unit_price, amount, payment_method, customer,"
                " source_text, created_at, day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, item.strip().lower(), quantity, int(unit_price), amount, payment_method, customer,
                 source_text, when.isoformat(timespec="seconds"), when.date().isoformat()),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def get(self, entry_id: int) -> Entry | None:
        row = self._conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return Entry(**dict(row)) if row else None

    def list(self, day: date | None = None, limit: int = 100) -> list[Entry]:
        if day:
            rows = self._conn.execute("SELECT * FROM entries WHERE day = ? ORDER BY id DESC LIMIT ?",
                                      (day.isoformat(), limit)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM entries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [Entry(**dict(r)) for r in rows]

    def undo_last(self) -> Entry | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM entries ORDER BY id DESC LIMIT 1").fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
            self._conn.commit()
            return Entry(**dict(row))

    def summary(self, day: date | None = None) -> dict:
        day = day or datetime.now(TZ).date()
        entries = self.list(day, limit=10_000)
        sales = [e for e in entries if e.kind == "sale"]
        expenses = [e for e in entries if e.kind == "expense"]
        cash_in = sum(e.amount for e in sales if e.payment_method != "hutang")
        credit = sum(e.amount for e in sales if e.payment_method == "hutang")
        spent = sum(e.amount for e in expenses)
        by_item: dict[str, int] = {}
        for e in sales:
            by_item[e.item] = by_item.get(e.item, 0) + e.amount
        top = sorted(by_item.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return {
            "day": day.isoformat(),
            "sales_total": sum(e.amount for e in sales),
            "cash_received": cash_in,
            "credit_outstanding": credit,
            "expenses_total": spent,
            "profit_estimate": sum(e.amount for e in sales) - spent,
            "transactions": len(entries),
            "top_items": [{"item": k, "amount": v} for k, v in top],
        }


def summary_sentence(s: dict) -> str:
    """A short spoken summary in Indonesian."""
    text = (f"Hari ini penjualan {rupiah(s['sales_total'])}, pengeluaran {rupiah(s['expenses_total'])}, "
            f"perkiraan untung {rupiah(s['profit_estimate'])}.")
    if s["credit_outstanding"]:
        text += f" Hutang pelanggan {rupiah(s['credit_outstanding'])}."
    return text
