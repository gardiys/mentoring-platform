from datetime import UTC, date, datetime, time


def learning_start_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=UTC)
