from app.career_packages.models import CareerPackage, CareerPackageStatus

ALLOWED_TRANSITIONS: dict[CareerPackageStatus, frozenset[CareerPackageStatus]] = {
    CareerPackageStatus.NOT_STARTED: frozenset(
        {CareerPackageStatus.COLLECTING_DATA, CareerPackageStatus.CANCELLED}
    ),
    CareerPackageStatus.COLLECTING_DATA: frozenset(
        {
            CareerPackageStatus.GENERATING,
            CareerPackageStatus.DRAFT,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.GENERATING: frozenset(
        {
            CareerPackageStatus.REVIEW_REQUIRED,
            CareerPackageStatus.COLLECTING_DATA,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.DRAFT: frozenset(
        {
            CareerPackageStatus.GENERATING,
            CareerPackageStatus.REVIEW_REQUIRED,
            CareerPackageStatus.READY_TO_PUBLISH,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.REVIEW_REQUIRED: frozenset(
        {
            CareerPackageStatus.DRAFT,
            CareerPackageStatus.GENERATING,
            CareerPackageStatus.READY_TO_PUBLISH,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.READY_TO_PUBLISH: frozenset(
        {
            CareerPackageStatus.DRAFT,
            CareerPackageStatus.GENERATING,
            CareerPackageStatus.DELIVERY_PENDING,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.DELIVERY_PENDING: frozenset(
        {
            CareerPackageStatus.PROVIDED,
            CareerPackageStatus.READY_TO_PUBLISH,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.PROVIDED: frozenset(
        {CareerPackageStatus.REVISION_REQUESTED, CareerPackageStatus.DRAFT}
    ),
    CareerPackageStatus.REVISION_REQUESTED: frozenset(
        {
            CareerPackageStatus.DRAFT,
            CareerPackageStatus.GENERATING,
            CareerPackageStatus.CANCELLED,
        }
    ),
    CareerPackageStatus.CANCELLED: frozenset({CareerPackageStatus.COLLECTING_DATA}),
}


def can_transition(current: CareerPackageStatus, target: CareerPackageStatus) -> bool:
    return current == target or target in ALLOWED_TRANSITIONS[current]


def transition(package: CareerPackage, target: CareerPackageStatus) -> None:
    current = package.status
    if not isinstance(current, CareerPackageStatus) or not can_transition(current, target):
        raise ValueError(f"Invalid career package transition: {current} -> {target}")
    package.status = target
