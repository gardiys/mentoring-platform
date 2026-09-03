from app.core.errors import api_error
from app.payments.models import EmploymentCaseStatus, StudentEmployment

ALLOWED_TRANSITIONS: dict[EmploymentCaseStatus, set[EmploymentCaseStatus]] = {
    EmploymentCaseStatus.REPORTED: {
        EmploymentCaseStatus.AWAITING_INITIAL_DOCUMENTS,
        EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES,
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.AWAITING_INITIAL_DOCUMENTS: {
        EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES,
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES: {
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.AWAITING_STAFF_REVIEW: {
        EmploymentCaseStatus.PROFILE_CONFIRMED,
        EmploymentCaseStatus.NON_PROFILE_CONFIRMED,
        EmploymentCaseStatus.MONITORING_NON_PROFILE,
        EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.NON_PROFILE_CONFIRMED: {
        EmploymentCaseStatus.MONITORING_NON_PROFILE,
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.MONITORING_NON_PROFILE: {
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.PROFILE_CONFIRMED,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
        EmploymentCaseStatus.CLOSED,
    },
    EmploymentCaseStatus.PROFILE_CONFIRMED: {
        EmploymentCaseStatus.AWAITING_STAFF_REVIEW,
        EmploymentCaseStatus.DISPUTED,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.DISPUTED: {
        EmploymentCaseStatus.PROFILE_CONFIRMED,
        EmploymentCaseStatus.NON_PROFILE_CONFIRMED,
        EmploymentCaseStatus.MONITORING_NON_PROFILE,
        EmploymentCaseStatus.AWAITING_ACTUAL_DUTIES,
        EmploymentCaseStatus.ENDED,
    },
    EmploymentCaseStatus.ENDED: {EmploymentCaseStatus.CLOSED},
    EmploymentCaseStatus.CLOSED: set(),
}


def transition(case: StudentEmployment, target: EmploymentCaseStatus) -> None:
    current = case.case_status
    if current is None:
        case.case_status = target
        return
    if target is current:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        api_error(
            409,
            "invalid_employment_case_transition",
            f"Employment case cannot move from {current.value} to {target.value}",
        )
    case.case_status = target
