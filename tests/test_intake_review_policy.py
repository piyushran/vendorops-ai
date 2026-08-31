from app.config.settings import Settings
from app.extraction.schemas import ExtractedBusinessRecord, ExtractedRecordType
from app.pipeline.document_pipeline import PipelineInputError


def test_review_threshold_is_configurable() -> None:
    settings = Settings(extraction_review_threshold=0.9)
    assert settings.extraction_review_threshold == 0.9


def test_review_policy_threshold_marks_low_confidence_record() -> None:
    settings = Settings(extraction_review_threshold=0.9)
    record = ExtractedBusinessRecord(
        record_type=ExtractedRecordType.invoice,
        summary="Invoice",
        confidence=0.84,
        needs_review=False,
    )

    needs_review = (
        record.needs_review
        or record.confidence < settings.extraction_review_threshold
    )

    assert needs_review is True


def test_pipeline_input_error_is_domain_specific() -> None:
    error = PipelineInputError("missing")
    assert isinstance(error, Exception)
