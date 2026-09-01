"""Provider-agnostic document classification for VendorOps intake."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class DocumentClass(StrEnum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    CONTRACT = "contract"
    TAX_DOCUMENT = "tax_document"
    VENDOR_MASTER = "vendor_master"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassificationResult:
    document_class: DocumentClass
    confidence: float
    reasons: tuple[str, ...]


_PATTERNS: tuple[tuple[DocumentClass, tuple[str, ...]], ...] = (
    (
        DocumentClass.INVOICE,
        (r"\binvoice\b", r"\binv[\s_-]?(?:no|number)\b", r"tax invoice"),
    ),
    (
        DocumentClass.PURCHASE_ORDER,
        (r"\bpurchase[\s_-]?order\b", r"\bpo[\s_-]?(?:no|number)\b"),
    ),
    (
        DocumentClass.CONTRACT,
        (r"\bcontract\b", r"\bagreement\b", r"terms and conditions"),
    ),
    (
        DocumentClass.TAX_DOCUMENT,
        (r"\btax\b", r"gst", r"vat", r"withholding", r"tax certificate"),
    ),
    (
        DocumentClass.VENDOR_MASTER,
        (
            r"vendor master",
            r"supplier master",
            r"vendor registration",
            r"supplier registration",
        ),
    ),
)


def classify_document(*, filename: str = "", text: str = "") -> ClassificationResult:
    """Classify a document using explainable filename/text signals.

    This first implementation deliberately favors precision and explainability.
    Ambiguous documents remain ``unknown`` instead of being routed into a
    potentially unsafe downstream automation path.
    """
    haystack = f"{filename}\n{text}".lower()
    scores: list[tuple[DocumentClass, int, list[str]]] = []

    for document_class, patterns in _PATTERNS:
        reasons: list[str] = []
        score = 0
        for pattern in patterns:
            if re.search(pattern, haystack, flags=re.IGNORECASE):
                score += 1
                reasons.append(f"matched:{pattern}")
        if score:
            scores.append((document_class, score, reasons))

    if not scores:
        return ClassificationResult(DocumentClass.UNKNOWN, 0.0, ("no_known_signals",))

    scores.sort(key=lambda item: item[1], reverse=True)
    winner, winner_score, reasons = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0

    # Require a clear lead when multiple classes have signals.
    if len(scores) > 1 and winner_score == second_score:
        return ClassificationResult(
            DocumentClass.UNKNOWN,
            0.25,
            ("ambiguous_signals", f"top_score:{winner_score}"),
        )

    confidence = min(0.95, 0.65 + (0.1 * (winner_score - 1)))
    return ClassificationResult(winner, confidence, tuple(reasons))
