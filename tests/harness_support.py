"""Reusable building blocks for the multi-user isolation harness.

The harness's central idea (paper Section "Methodology"): interleave requests
from two authenticated users and assert, at every layer, that no byte of one
user's data can reach the other user's LLM prompt. The layers checked are:

1. Identity      -- both users authenticate through the real JWT flow.
2. Retrieval     -- vector search results for A never carry B's session/user.
3. Session state -- the prompt string built for A never contains any of B's
                    turns; ``RecordingLLM`` captures the exact prompt that
                    would be sent to Ollama.
4. Reset scoping -- /chat/reset for A leaves B's stored turns intact.

Everything here is deliberately independent of pytest so the measurement
helpers can be reused from scripts, notebooks, or CI jobs.
"""

from __future__ import annotations

from typing import Any

from core.llm_engine import OllamaEngine

# ---------------------------------------------------------------------------
# Canary markers. These tokens are engineered to be unique enough that a
# substring scan over a prompt is conclusive evidence of cross-user leakage.
# ---------------------------------------------------------------------------
USER_A_MARKER = "ZEBRA-QUANTUM-LEDGER"
USER_B_MARKER = "ORCA-PHOTON-VAULT"

USER_A_DOC_TEXT = (
    f"Invoice from {USER_A_MARKER} Consulting\n"
    "Invoice Number: ZQL-0001\n"
    "Subtotal: 100.00\nTax: 5.00\nTotal: 105.00\n"
    "Line item: quantum ledger audit x2\n"
)
USER_B_DOC_TEXT = (
    f"Invoice from {USER_B_MARKER} Industries\n"
    "Invoice Number: OPV-0009\n"
    "Subtotal: 900.00\nTax: 45.00\nTotal: 945.00\n"
    "Line item: photon vault maintenance x3\n"
)

USER_A_QUESTIONS = [
    f"What is the total of the {USER_A_MARKER} invoice?",
    f"Which vendor issued invoice ZQL-0001 in my documents?",
]
USER_B_QUESTIONS = [
    f"How much tax did {USER_B_MARKER} charge?",
    f"What is the grand total for invoice OPV-0009?",
]


def session_id_for(user_id: int) -> str:
    """Mirror the server-side session derivation used by the API routes."""
    return f"user_{user_id}_default"


class RecordingLLM(OllamaEngine):
    """Test double that records the exact prompt built for every call.

    ``build_prompt`` is inherited unchanged from :class:`OllamaEngine`, so the
    captured strings are byte-for-byte what production would send to the local
    LLM -- including the conversation-history block. ``generate`` never touches
    the network: it returns a deterministic echo of the question so each HTTP
    response can be correlated back to exactly one recorded prompt.
    """

    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []
        self.responses: list[str] = []
        self.history_snapshots: list[list[dict[str, str]]] = []

    def generate(
        self,
        query: str,
        retrieved_items: list[dict[str, Any]],
        invoice_summaries: list[dict[str, Any]],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        prompt = self.build_prompt(query, retrieved_items, invoice_summaries, conversation_history)
        self.prompts.append(prompt)
        self.history_snapshots.append(list(conversation_history or []))
        response = f"[MOCK-ANSWER] {query}"
        self.responses.append(response)
        return response

    # -- correlation helpers -------------------------------------------------
    def prompts_containing(self, response_text: str) -> list[str]:
        """Return recorded prompts whose response equals ``response_text``.

        Because responses are unique echoes of unique questions, this maps an
        HTTP response observed by one user back to the exact prompt(s) built
        on that user's behalf -- without relying on thread-locality, which is
        not guaranteed under concurrent execution.
        """
        return [
            prompt
            for prompt, response in zip(self.prompts, self.responses)
            if response == response_text
        ]

    def all_prompts(self) -> list[str]:
        return list(self.prompts)


# ---------------------------------------------------------------------------
# Leakage measurement (the paper's headline metric).
# ---------------------------------------------------------------------------
def prompt_leaks(prompt: str, foreign_markers: list[str]) -> bool:
    """True if any foreign marker appears anywhere in the prompt string."""
    lowered = prompt.lower()
    return any(marker.lower() in lowered for marker in foreign_markers)


def leakage_rate(victim_prompts: list[str], foreign_markers: list[str]) -> float:
    """Fraction of victim prompts containing at least one foreign marker.

    0.0 == no observable cross-user leakage (post-fix expectation);
    >0.0 == measurable isolation failure (pre-fix expectation).
    """
    if not victim_prompts:
        return 0.0
    leaked = sum(1 for p in victim_prompts if prompt_leaks(p, foreign_markers))
    return leaked / len(victim_prompts)


def foreign_markers_for(user_marker: str, user_questions: list[str], other_marker: str, other_questions: list[str]) -> list[str]:
    """Markers proving 'other user' presence inside a victim's prompt.

    Includes the other user's document canary, their question texts, and the
    mock answers those questions produced (assistant-turn leakage).
    """
    markers = [other_marker, *other_questions]
    markers.extend(f"[MOCK-ANSWER] {q}" for q in other_questions)
    # The victim's own marker/questions must NOT be treated as foreign.
    return [m for m in markers if user_marker not in m]


# ---------------------------------------------------------------------------
# Run-scoped measurement registry (dumped to JSON by conftest).
# ---------------------------------------------------------------------------
REPORT: dict[str, list[dict[str, Any]]] = {
    "measurements": [],
    "prompt_audit": [],
}


def record_measurement(test: str, victim: str, rate: float, prompts_checked: int) -> None:
    REPORT["measurements"].append(
        {
            "test": test,
            "victim": victim,
            "leakage_rate": round(rate, 6),
            "prompts_checked": prompts_checked,
        }
    )


def record_prompt_audit(test: str, user: str, prompt: str, leaked: bool) -> None:
    REPORT["prompt_audit"].append(
        {
            "test": test,
            "user": user,
            "leaked": leaked,
            # Store only a short prefix: full prompts contain document text.
            "prompt_head": prompt[:160],
        }
    )
