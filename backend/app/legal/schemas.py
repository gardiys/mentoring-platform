from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class Questionnaire(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    employment_status: str = Field(min_length=2, max_length=100)
    position: str = Field(min_length=2, max_length=500)
    work_format: str = Field(min_length=2, max_length=500)
    technologies: str = Field(min_length=2, max_length=1000)
    existing_offers: StrictBool
    existing_offers_details: str = Field(default="", max_length=2000)
    selection_processes: StrictBool
    selection_processes_details: str = Field(default="", max_length=2000)
    previous_obligations: StrictBool
    previous_obligations_details: str = Field(default="", max_length=2000)
    go_in_current_work: StrictBool = False
    go_in_current_work_details: str = Field(default="", max_length=2000)
    previous_contract: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_details(self) -> Questionnaire:
        for name in (
            "existing_offers",
            "selection_processes",
            "previous_obligations",
            "go_in_current_work",
        ):
            if getattr(self, name) and not getattr(self, f"{name}_details"):
                raise ValueError(f"Explanation required for {name}")
        return self


class CheckoutConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_offer_version_id: UUID
    questionnaire_schema_version: Literal[1]
    answers: Questionnaire
    confirmations: dict[str, StrictBool]
    page_identifier: str = Field(min_length=1, max_length=200)
    frontend_build_version: str | None = Field(default=None, max_length=100)


class EmailCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{8}$")


class OfferStatus(BaseModel):
    status: Literal["active", "retired", "revoked"]


class ContractState(BaseModel):
    status: Literal["terminated", "refunded", "disputed"]
    external_event_id: str = Field(min_length=1, max_length=150)
    amount_minor: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
