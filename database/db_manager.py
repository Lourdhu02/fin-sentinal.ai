from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings
from models.invoice import Invoice
from models.user import User

_local = threading.local()


class DatabaseManager:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.settings = get_settings()
        self.db_path = Path(db_path or self.settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @property
    def connection(self) -> sqlite3.Connection:
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA foreign_keys = ON")
            _local.conn.execute("PRAGMA journal_mode = WAL")
        return _local.conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with schema_path.open("r", encoding="utf-8") as f:
            schema = f.read()
        self.connection.executescript(schema)
        self.connection.commit()

    def close(self) -> None:
        if hasattr(_local, "conn") and _local.conn:
            _local.conn.close()
            _local.conn = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_invoice(self, row: sqlite3.Row | None) -> Invoice | None:
        if row is None:
            return None
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return Invoice(
            id=row["id"],
            invoice_number=row["invoice_number"],
            vendor_name=row["vendor_name"],
            document_path=row["document_path"],
            subtotal=float(row["subtotal"]),
            tax=float(row["tax"]),
            total=float(row["total"]),
            currency=row["currency"],
            content=row["content"],
            content_hash=row["content_hash"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=metadata,
        )

    def create_user(self, username: str, password_hash: str, role: str = "user") -> User:
        cursor = self.connection.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, role, 1, self._now()),
        )
        self.connection.commit()
        return self.get_user_by_id(cursor.lastrowid)

    def get_user(self, username: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "password_hash": str(row["password_hash"]),
            "role": str(row["role"]),
            "is_active": bool(row["is_active"]),
            "created_at": str(row["created_at"]),
        }

    def get_user_by_id(self, user_id: int) -> User | None:
        row = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row)

    def get_user_by_username(self, username: str) -> User | None:
        record = self.get_user(username)
        if record is None:
            return None
        return User(
            id=record["id"],
            username=record["username"],
            password_hash=record["password_hash"],
            role=record["role"],
            is_active=record["is_active"],
            created_at=datetime.fromisoformat(record["created_at"]),
        )

    def list_users(self) -> list[User]:
        rows = self.connection.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [u for row in rows if (u := self._row_to_user(row)) is not None]

    def update_user_role(self, user_id: int, role: str) -> User | None:
        self.connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        self.connection.commit()
        return self.get_user_by_id(user_id)

    def create_invoice(self, invoice: Invoice) -> Invoice:
        cursor = self.connection.execute(
            """
            INSERT INTO invoices (
                invoice_number, vendor_name, document_path, subtotal, tax, total,
                currency, content, content_hash, metadata_json, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice.invoice_number, invoice.vendor_name, invoice.document_path,
                invoice.subtotal, invoice.tax, invoice.total, invoice.currency,
                invoice.content, invoice.content_hash, json.dumps(invoice.metadata),
                invoice.created_by, invoice.created_at.isoformat(),
            ),
        )
        self.connection.commit()
        return self.get_invoice_by_id(cursor.lastrowid)

    def get_invoice_by_id(self, invoice_id: int) -> Invoice | None:
        row = self.connection.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        return self._row_to_invoice(row)

    def get_invoice_by_hash(self, content_hash: str) -> Invoice | None:
        row = self.connection.execute(
            "SELECT * FROM invoices WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return self._row_to_invoice(row)

    def list_invoices(self, user_id: int) -> list[Invoice]:
        rows = self.connection.execute("SELECT * FROM invoices WHERE created_by = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [inv for row in rows if (inv := self._row_to_invoice(row)) is not None]

    def get_all_invoices(self, user_id: int) -> list[Invoice]:
        return self.list_invoices(user_id)

    def get_invoices_by_vendor(self, vendor_name: str, user_id: int) -> list[Invoice]:
        rows = self.connection.execute(
            "SELECT * FROM invoices WHERE LOWER(vendor_name) LIKE LOWER(?) AND created_by = ?",
            (f"%{vendor_name}%", user_id),
        ).fetchall()
        return [inv for row in rows if (inv := self._row_to_invoice(row)) is not None]

    def get_invoices_above_total(self, threshold: float, user_id: int) -> list[Invoice]:
        rows = self.connection.execute(
            "SELECT * FROM invoices WHERE total >= ? AND created_by = ? ORDER BY total DESC", (threshold, user_id)
        ).fetchall()
        return [inv for row in rows if (inv := self._row_to_invoice(row)) is not None]

    def get_all_line_items(self, user_id: int) -> list[dict]:
        items: list[dict] = []
        for invoice in self.get_all_invoices(user_id):
            items.extend(self._extract_line_items(invoice))
        return items

    def get_invoices_by_ids(self, invoice_ids: list[int], user_id: int) -> list[Invoice]:
        if not invoice_ids:
            return []
        placeholders = ",".join("?" for _ in invoice_ids)
        params = invoice_ids + [user_id]
        rows = self.connection.execute(
            f"SELECT * FROM invoices WHERE id IN ({placeholders}) AND created_by = ?", params
        ).fetchall()
        return [inv for row in rows if (inv := self._row_to_invoice(row)) is not None]

    def get_invoice_totals(self, user_id: int, exclude_invoice_id: int | None = None) -> list[float]:
        if exclude_invoice_id is None:
            rows = self.connection.execute("SELECT total FROM invoices WHERE created_by = ?", (user_id,)).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT total FROM invoices WHERE created_by = ? AND id != ?", (user_id, exclude_invoice_id)
            ).fetchall()
        return [float(row["total"]) for row in rows]

    def get_vendor_summary(self, user_id: int) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT vendor_name,
                   COUNT(*) as invoice_count,
                   SUM(total) as total_spend,
                   AVG(total) as avg_invoice,
                   MAX(total) as max_invoice,
                   MIN(total) as min_invoice
            FROM invoices
            WHERE created_by = ?
            GROUP BY LOWER(vendor_name)
            ORDER BY total_spend DESC
            """, (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def create_audit_log(
        self,
        user_id: int | None,
        action: str,
        query_text: str,
        response_text: str,
        query_hash: str,
        response_hash: str,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO audit_logs (user_id, action, query_text, response_text, query_hash, response_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, query_text, response_text, query_hash, response_hash, self._now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def list_audit_logs(self, limit: int = 50) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def _extract_line_items(self, invoice: Invoice) -> list[dict]:
        items: list[dict] = []
        lines = [line.strip() for line in invoice.content.splitlines() if line.strip()]
        ignored_tokens = {
            "invoice", "vendor", "seller", "from", "subtotal", "tax", "vat",
            "gst", "cgst", "sgst", "igst", "total", "amount due", "grand total", "invoice total",
        }
        for line in lines:
            lowered = line.lower()
            if any(token in lowered for token in ignored_tokens):
                continue
            leading = re.search(
                r"(?i)\b(?P<qty>\d+(?:\.\d+)?)\s*(?:x|units?|pcs?|pieces?)?\s+(?P<desc>[a-z][a-z0-9 /&().,_-]{2,})$",
                line,
            )
            trailing = re.search(
                r"(?i)^(?P<desc>[a-z][a-z0-9 /&().,_-]{2,}?)\s+(?:x|qty|quantity|units?|pcs?|pieces?)?\s*(?P<qty>\d+(?:\.\d+)?)$",
                line,
            )
            embedded = re.search(
                r"(?i)\b(?P<desc>[a-z][a-z0-9 /&().,_-]{2,}?)\s+(?P<qty>\d+(?:\.\d+)?)\b",
                line,
            )
            match = leading or trailing or embedded
            if match is None:
                continue
            description = re.sub(r"\s+", " ", match.group("desc")).strip(" -:")
            quantity = self._normalize_quantity(match.group("qty"))
            if not description or quantity <= 0:
                continue
            items.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "description": description,
                "quantity": quantity,
            })
        return items

    def _normalize_quantity(self, raw: str) -> int:
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            return 0
