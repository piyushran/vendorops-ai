import pytest

from app.workflows.vendor_case import InvalidTransition, VendorCase, VendorCaseState


def test_vendor_case_follows_approval_before_execution() -> None:
    case = VendorCase("case-1")

    case = case.transition(VendorCaseState.UNDER_REVIEW)
    case = case.transition(VendorCaseState.READY_FOR_APPROVAL)
    case = case.transition(VendorCaseState.APPROVED)
    case = case.transition(VendorCaseState.EXECUTING)
    case = case.transition(VendorCaseState.COMPLETED)

    assert case.state is VendorCaseState.COMPLETED


def test_execution_cannot_skip_approval() -> None:
    case = VendorCase("case-2").transition(VendorCaseState.UNDER_REVIEW)

    with pytest.raises(InvalidTransition):
        case.transition(VendorCaseState.EXECUTING)


def test_completed_case_cannot_restart() -> None:
    case = VendorCase("case-3")
    for state in (
        VendorCaseState.UNDER_REVIEW,
        VendorCaseState.READY_FOR_APPROVAL,
        VendorCaseState.APPROVED,
        VendorCaseState.EXECUTING,
        VendorCaseState.COMPLETED,
    ):
        case = case.transition(state)

    with pytest.raises(InvalidTransition):
        case.transition(VendorCaseState.EXECUTING)
