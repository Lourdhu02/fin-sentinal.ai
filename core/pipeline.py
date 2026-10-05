from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from core.anomaly import AnomalyDetector
from core.embedder import LocalEmbedder
from core.extractor import UniversalExtractor
from core.ingestion import IngestionService
from core.llm_engine import OllamaEngine
from core.retriever import Retriever
from core.verifier import InvoiceVerifier
from database.db_manager import DatabaseManager
from database.vector_store import ChromaDBVectorStore
from models.invoice import Invoice
from security.audit_logger import AuditLogger

# Maximum number of turns (user + assistant messages) retained per session.
_MAX_HISTORY_TURNS = 20


class FinSentinelPipeline:
    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        ingestion_service: IngestionService | None = None,
        embedder: LocalEmbedder | None = None,
        vector_store: ChromaDBVectorStore | None = None,
        verifier: InvoiceVerifier | None = None,
        anomaly_detector: AnomalyDetector | None = None,
        llm_engine: OllamaEngine | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.db = db_manager or DatabaseManager()
        self.ingestion = ingestion_service or IngestionService()
        self.embedder = embedder or LocalEmbedder()
        self.vector_store = vector_store or ChromaDBVectorStore()
        self.retriever = Retriever(self.embedder, self.vector_store)
        self.verifier = verifier or InvoiceVerifier()
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.llm_engine = llm_engine or OllamaEngine()
        self.audit_logger = audit_logger or AuditLogger(self.db)
        self.extractor = UniversalExtractor()
        # Conversation state is keyed by session_id so that concurrent users
        # sharing this pipeline instance can never observe each other's turns.
        # NOTE: never store conversation state as a plain instance-level list;
        # this pipeline is instantiated once per process by the API layer.
        self._conversation_history: dict[str, list[dict[str, str]]] = {}
        self._history_lock = threading.Lock()

    def ingest_and_store(self, source_path: str | Path, session_id: str, user_id: int | None = None) -> dict[str, Any]:
        path = Path(source_path)
        source_files = self.ingestion.get_supported_files(path)
        documents = self.ingestion.ingest(path)
        processed: list[dict[str, Any]] = []
        stored_count = error_count = 0

        for document in documents:
            try:
                source_text = document.text if document.text else ""
                if document.error and not source_text:
                    raise ValueError(document.error)
                
                chunks = self._chunk_text(source_text)
                embeddings = self.embedder.embed_texts(chunks)
                metadata = [
                    {
                        "session_id": session_id,
                        "document_path": document.path,
                        "text": chunk,
                        "chunk_index": index,
                        "file_name": Path(document.path).name,
                    }
                    for index, chunk in enumerate(chunks)
                ]
                # Defense-in-depth: record the owning user alongside the
                # session so cross-user access is detectable/auditable even if
                # session_id semantics change later. ChromaDB rejects None
                # metadata values, so user_id is only set when known.
                if user_id is not None:
                    for meta in metadata:
                        meta["user_id"] = int(user_id)
                self.vector_store.add(embeddings, metadata)
                stored_count += 1
                processed.append({
                    "path": document.path,
                    "status": "stored",
                    "file_name": Path(document.path).name,
                })
            except Exception as exc:
                error_count += 1
                processed.append({"path": document.path, "status": "error", "error": str(exc)})

        self.vector_store.save()
        return {
            "processed_count": len(source_files),
            "stored_count": stored_count,
            "error_count": error_count,
            "success_count": stored_count,
            "failed_count": max(0, len(source_files) - stored_count),
            "documents": processed,
        }

    def query(self, question: str, session_id: str, user_id: int | None = None, top_k: int = 20) -> dict[str, Any]:
        # Perform session-based retrieval
        query_embedding = self.retriever.embedder.embed_query(question)
        results = self.vector_store.search(query_embedding, top_k=top_k, filter_dict={"session_id": session_id})
        
        # Optional: rerank
        results = self.retriever.rerank(question, results, top_n=10)

        # Only the calling session's turns are visible to the LLM prompt.
        with self._history_lock:
            history = list(self._conversation_history.get(session_id, []))

        response = self.llm_engine.generate(
            question,
            results,
            [], # no longer using invoice summaries
            conversation_history=history[-6:],
        )

        with self._history_lock:
            session_history = self._conversation_history.setdefault(session_id, [])
            session_history.append({"role": "user", "content": question})
            session_history.append({"role": "assistant", "content": response})
            if len(session_history) > _MAX_HISTORY_TURNS:
                del session_history[:-_MAX_HISTORY_TURNS]

        self.audit_logger.log_interaction(user_id, "query", question, response)
        return {"query": question, "response": response, "results": results}

    def reset_conversation(self, session_id: str) -> int:
        """Clear conversation history for exactly one session.

        Requires an explicit ``session_id`` so callers cannot accidentally
        wipe every user's history (the pre-fix global behaviour).

        Returns the number of turns that were removed.
        """
        if not session_id:
            raise ValueError("session_id is required to reset a conversation.")
        with self._history_lock:
            removed = self._conversation_history.pop(session_id, [])
        return len(removed)

    def conversation_turns(self, session_id: str) -> list[dict[str, str]]:
        """Return a copy of the stored turns for a session (introspection/testing)."""
        with self._history_lock:
            return list(self._conversation_history.get(session_id, []))

    def _build_invoice(self, document_path: str | Path, text: str, user_id: int | None) -> Invoice:
        safe_text = text if text and text.strip() else Path(document_path).stem
        try:
            extracted = self.extractor.extract(safe_text, document_path)
            fields = self.extractor.to_invoice_fields(extracted)
            return Invoice.from_extracted(fields, safe_text, document_path, created_by=user_id)
        except Exception:
            try:
                return Invoice.from_text(safe_text, document_path, created_by=user_id)
            except Exception:
                return Invoice.from_text(Path(document_path).stem, document_path, created_by=user_id)

    def _rich_text(self, invoice: Invoice) -> str:
        meta = invoice.metadata
        parts = [invoice.content]
        extras: list[str] = []

        kind = meta.get("kind", "")
        if kind == "salary_slip":
            extras = [
                f"Employee: {meta.get('employee_name', '')}",
                f"Employee ID: {meta.get('employee_id', '')}",
                f"Period: {meta.get('period', '')}",
                f"Net Pay: {invoice.total}",
                f"Gross Earnings: {meta.get('gross_earnings', '')}",
                f"Basic Salary: {meta.get('basic_salary', '')}",
                f"HRA: {meta.get('hra', '')}",
                f"TDS: {meta.get('tds', '')}",
                f"PF: {meta.get('pf', '')}",
                f"Total Deductions: {meta.get('total_deductions', '')}",
            ]
        elif kind == "bank_statement":
            extras = [
                f"Account: {meta.get('account_number', '')}",
                f"Period: {meta.get('period', '')}",
                f"Opening Balance: {meta.get('opening_balance', '')}",
                f"Closing Balance: {meta.get('closing_balance', '')}",
                f"Total Credits: {meta.get('total_credits', '')}",
                f"Total Debits: {meta.get('total_debits', '')}",
            ]
        elif kind == "gst_return":
            extras = [
                f"GSTIN: {meta.get('gstin', '')}",
                f"Period: {meta.get('period', '')}",
                f"Taxable Value: {meta.get('taxable_value', '')}",
                f"CGST: {meta.get('cgst', '')}",
                f"SGST: {meta.get('sgst', '')}",
                f"IGST: {meta.get('igst', '')}",
                f"Total Tax: {invoice.tax}",
            ]
        elif kind == "credit_debit_note":
            extras = [
                f"Note Type: {meta.get('note_type', '')}",
                f"Original Invoice: {meta.get('original_invoice', '')}",
                f"Reason: {meta.get('reason', '')}",
                f"Amount: {invoice.total}",
            ]
        elif kind == "purchase_order":
            extras = [
                f"PO Number: {meta.get('po_number', invoice.invoice_number)}",
                f"Delivery Date: {meta.get('delivery_date', '')}",
                f"Payment Terms: {meta.get('payment_terms', '')}",
                f"PO Total: {invoice.total}",
            ]
        elif kind == "invoice":
            extras = [
                f"Invoice Number: {invoice.invoice_number}",
                f"GSTIN: {meta.get('gstin', '')}",
                f"Subtotal: {invoice.subtotal}",
                f"Tax: {invoice.tax}",
                f"Total: {invoice.total}",
            ]

        parts.extend(e for e in extras if e.split(": ", 1)[-1].strip())
        return "\n".join(parts)

    def _build_invoice_summaries(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for result in results:
            invoice_id = result.get("invoice_id")
            if not isinstance(invoice_id, int) or invoice_id in seen_ids:
                continue
            invoice = self.db.get_invoice_by_id(invoice_id)
            if invoice is None:
                continue
            verification = self.verifier.verify_invoice(invoice, self.db)
            anomaly = self.anomaly_detector.score(
                invoice.total,
                self.db.get_invoice_totals(exclude_invoice_id=invoice.id),
            )
            anomaly_dict = anomaly.model_dump()
            anomaly_dict["explanation"] = invoice.metadata.get("anomaly", {}).get("explanation", "")
            
            summaries.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "vendor_name": invoice.vendor_name,
                "kind": invoice.metadata.get("kind", "unknown"),
                "total": invoice.total,
                "subtotal": invoice.subtotal,
                "tax": invoice.tax,
                "currency": invoice.currency,
                "metadata": {
                    k: v for k, v in invoice.metadata.items()
                    if k not in ("verification", "anomaly", "file_type")
                },
                "verification": verification.model_dump(),
                "anomaly": anomaly_dict,
            })
            seen_ids.add(invoice_id)
        return summaries

    def _handle_structured_query(self, route: dict[str, Any], question: str) -> str | None:
        kind = str(route.get("kind", "llm"))
        if kind == "total":
            invoices = self.db.get_all_invoices()
            total_spend = sum(float(inv.total) for inv in invoices)
            symbol = self._currency_symbol(invoices)
            return f"Total spend across {len(invoices)} documents: {symbol}{self._format_number(total_spend)}"
        if kind == "count":
            target = route.get("target")
            if not target:
                return None
            count = self._count_items(str(target))
            label = self._pluralize_target(str(target), count)
            return f"Total {label} purchased: {count}"
        if kind == "vendor_summary":
            summaries = self.db.get_vendor_summary()
            if not summaries:
                return "No vendor data found."
            lines = ["Vendor spend summary:"]
            for s in summaries[:10]:
                lines.append(
                    f"  {s['vendor_name']}: {s['invoice_count']} documents, "
                    f"total = {self._format_number(s['total_spend'])}"
                )
            return "\n".join(lines)
        return None

    def _count_items(self, target: str) -> int:
        normalized_target = self._normalize_target(target)
        line_items = self.db.get_all_line_items()
        total_quantity = 0
        matched = False
        for item in line_items:
            description = self._normalize_target(str(item.get("description", "")))
            if normalized_target and normalized_target in description:
                total_quantity += int(item.get("quantity", 0))
                matched = True
        if matched:
            return total_quantity
        invoices = self.db.get_all_invoices()
        fallback_total = 0
        for invoice in invoices:
            for line in invoice.content.splitlines():
                if normalized_target not in self._normalize_target(line.lower()):
                    continue
                fallback_total += self._extract_quantity_from_line(line)
        return fallback_total

    def _extract_quantity_from_line(self, line: str) -> int:
        for pattern in [
            r"(?i)\b(\d+)\s*(?:x|units?|pcs?|pieces?)?\s+[a-z]",
            r"(?i)[a-z]\s+(?:x|qty|quantity|units?|pcs?|pieces?)?\s*(\d+)\b",
        ]:
            m = re.search(pattern, line)
            if m:
                return max(0, int(m.group(1)))
        return 1

    def _normalize_target(self, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned.endswith("s") and len(cleaned) > 3:
            cleaned = cleaned[:-1]
        return cleaned

    def _pluralize_target(self, target: str, count: int) -> str:
        normalized = target.strip().lower()
        if count == 1:
            return normalized[:-1] if normalized.endswith("s") and len(normalized) > 3 else normalized
        return normalized if normalized.endswith("s") else f"{normalized}s"

    def _currency_symbol(self, invoices: list[Invoice]) -> str:
        counts: dict[str, int] = {}
        for inv in invoices:
            c = inv.currency or "INR"
            counts[c] = counts.get(c, 0) + 1
        if not counts:
            return "â‚¹"
        primary = max(counts, key=counts.__getitem__)
        return {"INR": "â‚¹", "USD": "$", "EUR": "â‚¬", "GBP": "Â£"}.get(primary, "â‚¹")

    def _format_number(self, value: float) -> str:
        rounded = round(value, 2)
        if abs(rounded - int(rounded)) < 1e-9:
            return f"{int(rounded):,}"
        return f"{rounded:,.2f}"

    def _chunk_text(self, text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return [""]
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + chunk_size)
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(0, end - overlap)
        return chunks
