"""Vendor case workflow state machine.

This module contains policy-safe workflow transitions only. External actions are
represented as explicit states and must be executed by a future integration
adapter after any required approval gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VendorCaseState(StrEnum):
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class InvalidTransition(ValueError):
    """Raised when a vendor case attempts an unsafe state transition."""


_ALLOWED: dict[VendorCaseState, frozenset[VendorCaseState]] = {
    VendorCaseState.RECEIVED: frozenset({VendorCaseState.UNDER_REVIEW}),
    VendorCaseState.UNDER_REVIEW: frozenset({
        VendorCaseState.READY_FOR_APPROVAL,
        VendorCaseState.FAILED,
    }),
    VendorCaseState.READY_FOR_APPROVAL: frozenset({
        VendorCaseState.APPROVED,
        VendorCaseState.FAILED,
    }),
    VendorCaseState.APPROVED: frozenset({VendorCaseState.EXECUTING}),
    VendorCaseState.EXECUTING: frozenset({
        VendorCaseState.COMPLETED,
        VendorCaseState.FAILED,
    }),
    VendorCaseState.COMPLETED: frozenset(),
    VendorCaseState.FAILED: frozenset(),
}


@dataclass(frozen=True)
class VendorCase:
    case_id: str
    state: VendorCaseState = VendorCaseState.RECEIVED

    def transition(self, target: VendorCaseState) -> VendorCase:
        """Return a new case after validating the requested transition."""
        allowed = _ALLOWED[self.state]
        if target not in allowed:
            raise InvalidTransition(
                f"Cannot transition vendor case from '{self.state}' to '{target}'."
            )
        return VendorCase(case_id=self.case_id, state=target)
