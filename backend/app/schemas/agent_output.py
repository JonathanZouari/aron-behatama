"""פלט מובנה של סוכן ה-AI. השרת מאמת אותו ואינו סומך על קביעות המודל."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .wardrobe_spec import SpecPatch


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(max_length=1500, description="תשובה ללקוח בעברית")
    proposed_spec_patch: SpecPatch = Field(default_factory=SpecPatch)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    requires_manual_review: bool = False
    manual_review_reasons: list[str] = Field(default_factory=list, max_length=10)
