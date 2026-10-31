from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import get_settings
from core.local_http import post_json, validate_endpoint


class OllamaEngine:
    def __init__(self, model_name: str | None = None, endpoint: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = model_name or self.settings.model_name
        self.endpoint = endpoint or os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/generate")
        validate_endpoint(self.endpoint)

    def build_prompt(
        self,
        query: str,
        retrieved_items: list[dict[str, Any]],
        invoice_summaries: list[dict[str, Any]],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        context_blocks: list[str] = []
        for i, item in enumerate(retrieved_items, 1):
            snippet = str(item.get("text", "")).strip()[:1500]
            context_blocks.append(
                f"[Evidence {i}]\n"
                f"Vendor: {item.get('vendor_name', 'unknown')}\n"
                f"Invoice#: {item.get('invoice_number', 'unknown')}\n"
                f"Path: {item.get('document_path', 'unknown')}\n"
                f"Relevance Score: {item.get('score', 0.0):.4f}\n"
                f"Text: {snippet}"
            )

        summary_blocks = [json.dumps(s, ensure_ascii=False) for s in invoice_summaries]
        joined_context = "\n\n".join(context_blocks) or "No retrieval context available."
        joined_summaries = "\n".join(summary_blocks) or "No invoice summaries available."

        history_block = ""
        if conversation_history:
            lines = []
            for turn in conversation_history:
                role = "User" if turn["role"] == "user" else "Assistant"
                lines.append(f"{role}: {turn['content']}")
            history_block = "Conversation History:\n" + "\n".join(lines) + "\n\n"

        return (
            "You are FinSentinelAI, a precise local financial analysis assistant.\n\n"
            "Rules:\n"
            "1. Answer ONLY from the supplied context and invoice data below.\n"
            "2. Always cite invoice numbers and vendor names when referencing specific invoices.\n"
            "3. If the answer is not in the context, say 'I don't have enough data to answer this.'\n"
            "4. Flag anomalies or verification issues if present in the data.\n"
            "5. Do NOT invent numbers. If a calculation is needed, show your working.\n"
            "6. Be concise but complete.\n\n"
            f"{history_block}"
            f"Current Question:\n{query}\n\n"
            f"Retrieved Evidence:\n{joined_context}\n\n"
            f"Structured Invoice & Anomaly Data:\n{joined_summaries}\n"
        )

    def generate(
        self,
        query: str,
        retrieved_items: list[dict[str, Any]],
        invoice_summaries: list[dict[str, Any]],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        if not retrieved_items:
            return "I don't have enough evidence to answer this question."
        prompt = self.build_prompt(query, retrieved_items, invoice_summaries, conversation_history)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024, "num_ctx": 4096},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            data = post_json(self.endpoint, payload)
            text = str(data.get("response", "")).strip()
            if text:
                return text
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Local generation service unavailable") from exc
        raise RuntimeError("Local generation returned an empty response")

    def generate_direct(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            data = post_json(self.endpoint, payload)
            return str(data.get("response", "")).strip()
        except Exception:
            return "Unable to generate explanation (LLM unavailable)."

    def _fallback_response(
        self,
        query: str,
        retrieved_items: list[dict[str, Any]],
        invoice_summaries: list[dict[str, Any]],
    ) -> str:
        if not retrieved_items:
            return f"No indexed invoice context found for: {query}"
        lines = [f"Query: {query}", "Retrieved evidence (Ollama unavailable):"]
        for item in retrieved_items[:5]:
            lines.append(
                f"  - {item.get('vendor_name', 'unknown')} / "
                f"{item.get('invoice_number', 'unknown')} / "
                f"{item.get('document_path', 'unknown')}"
            )
            snippet = str(item.get("text", "")).replace("\n", " ").strip()
            lines.append(f"    {snippet[:240]}")
        if invoice_summaries:
            lines.append("Invoice anomaly/verification data:")
            for s in invoice_summaries[:5]:
                lines.append(f"  {json.dumps(s, ensure_ascii=False)}")
        return "\n".join(lines)
