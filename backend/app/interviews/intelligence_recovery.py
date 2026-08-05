from __future__ import annotations

from app.interviews.intelligence_models import IntelligenceProcessingStatus


def intelligence_recovery_job_name(
    status: IntelligenceProcessingStatus,
    *,
    transcription_provider_job_id: str | None,
    candidate_speaker_selected: bool,
    extraction_completed: bool,
) -> str | None:
    """Return the idempotent worker job that can resume a persisted pipeline state."""
    if status is IntelligenceProcessingStatus.UPLOADED:
        return "submit_transcription"
    if status in {
        IntelligenceProcessingStatus.TRANSCRIPTION_SUBMITTED,
        IntelligenceProcessingStatus.TRANSCRIBING,
    }:
        return (
            "poll_transcription"
            if transcription_provider_job_id is not None
            else "submit_transcription"
        )
    if status is IntelligenceProcessingStatus.TRANSCRIPT_READY:
        return "process_transcription_result"
    if status is IntelligenceProcessingStatus.ANALYZING and candidate_speaker_selected:
        return "generate_answer_reviews" if extraction_completed else "extract_interview_structure"
    return None
