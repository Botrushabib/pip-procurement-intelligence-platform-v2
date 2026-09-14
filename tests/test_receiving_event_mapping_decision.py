from datetime import datetime

from app.services.receiving_event_mapping_decision import (
    ReceivingDecisionStatus,
    ReceivingReasonCode,
)
from app.services.receiving_event_mapping_result import (
    CompanyMetadata,
    WarehouseCandidate,
)
from tests.test_receiving_event_mapping_engine import make_row, mapped


def test_ready_requires_every_mapping_and_only_ready_is_persistable():
    ready = mapped(make_row()).decisions[0]
    review = mapped(make_row(), suppliers=[]).decisions[0]
    rejected = mapped(make_row(), company_metadata=CompanyMetadata()).decisions[0]

    assert ready.decision_status is ReceivingDecisionStatus.READY
    assert ready.eligible_for_persistence is True
    assert review.decision_status is ReceivingDecisionStatus.REVIEW
    assert review.eligible_for_persistence is False
    assert rejected.decision_status is ReceivingDecisionStatus.REJECTED
    assert rejected.eligible_for_persistence is False


def test_document_field_conflict_marks_all_document_rows_for_review():
    result = mapped(
        make_row(source_row=2),
        make_row(source_row=3, raw_destination="Backup Stores/Stock"),
        warehouses=[
            WarehouseCandidate(5, "Main Stores/Stock"),
            WarehouseCandidate(6, "Backup Stores/Stock"),
        ],
    )

    assert all(decision.decision_status is ReceivingDecisionStatus.REVIEW for decision in result.decisions)
    assert all(ReceivingReasonCode.DOCUMENT_GROUPING_CONFLICT.value in decision.reason_codes for decision in result.decisions)


def test_decision_keeps_mapping_and_raw_provenance():
    decision = mapped(make_row())[0] if False else mapped(make_row()).decisions[0]
    assert decision.company_id == 1
    assert decision.product_id == 3
    assert decision.line_result.row.raw_product == "[162017] Sugar Brown Portion TLT"
    assert decision.reason_codes == ()


def test_event_date_document_conflict_marks_all_matching_reference_rows_for_review():
    result = mapped(
        make_row(source_row=2, event_date_candidate=datetime(2026, 8, 15)),
        make_row(source_row=3, event_date_candidate=datetime(2026, 8, 16)),
    )

    assert all(decision.decision_status is ReceivingDecisionStatus.REVIEW for decision in result.decisions)
    assert all(
        decision.reason_codes == (ReceivingReasonCode.DOCUMENT_GROUPING_CONFLICT.value,)
        for decision in result.decisions
    )