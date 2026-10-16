from pydantic import BaseModel, Field


class OpportunitySummary(BaseModel):
    needs_action_total: int = 0
    overdue_total: int = 0
    consultations: dict[str, int] = Field(default_factory=dict)
    go_transition: dict[str, int] = Field(default_factory=dict)
    python_repeat: dict[str, int] = Field(default_factory=dict)
