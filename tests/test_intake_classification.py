from app.intake.classification import DocumentClass, classify_document


def test_classifies_invoice_from_filename_and_text() -> None:
    result = classify_document(
        filename="ACME_Invoice_1042.pdf",
        text="Tax invoice\nInvoice Number: 1042\nTotal: 1200",
    )

    assert result.document_class is DocumentClass.INVOICE
    assert result.confidence >= 0.75
    assert result.reasons


def test_classifies_purchase_order() -> None:
    result = classify_document(
        filename="PO-8841.pdf",
        text="Purchase Order\nSupplier: ACME",
    )

    assert result.document_class is DocumentClass.PURCHASE_ORDER


def test_ambiguous_document_is_not_trusted() -> None:
    result = classify_document(
        filename="tax-contract.pdf",
        text="Agreement between supplier and customer containing GST terms",
    )

    assert result.document_class is DocumentClass.UNKNOWN
    assert result.confidence < 0.5


def test_unknown_document_returns_zero_confidence() -> None:
    result = classify_document(filename="notes.txt", text="Meeting notes")

    assert result.document_class is DocumentClass.UNKNOWN
    assert result.confidence == 0.0
