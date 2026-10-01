"""Conservative ASR evidence; confidence is not a candidate knowledge score."""
from collections.abc import Mapping


def low_recognition_confidence(quality: Mapping[str, object] | None) -> bool:
    value = (quality or {}).get("low_confidence_fraction")
    return isinstance(value, int | float) and value >= 0.3
