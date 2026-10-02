from pydantic import BaseModel, Field, field_validator


class Meeting(BaseModel):
    """One meeting of a section (a section may list several, e.g. Fall + Spring)."""

    date: str = Field(
        default="",
        description=(
            "Meeting date(s) exactly as shown on the page. A date without a "
            "year uses the year listed in the HTML. Empty if not announced."
        ),
    )
    location: str = Field(
        default="",
        description="Venue and city/state of the meeting. Empty if not announced.",
    )
    speakers: str = Field(
        default="",
        description=(
            "All speaker names for this meeting together in this one field, "
            "comma separated. Empty if not announced."
        ),
    )

    @field_validator("date", "location", "speakers", mode="before")
    @classmethod
    def _normalize_text(cls, value):
        # The MAA page contains &nbsp; entities that surface as \xa0 in
        # extracted text, breaking cache lookups and geocoding queries.
        if isinstance(value, str):
            return " ".join(value.replace("\xa0", " ").split())
        return value


class SectionMeetings(BaseModel):
    """All meetings for one MAA section, extracted from the section-meetings page."""

    row_id: str = Field(
        description="Row identifier from the page HTML, e.g. 'row-0'. Use the exact value provided."
    )
    section: str = Field(
        default="",
        description="MAA section name, exactly as provided.",
    )
    section_url: str = Field(
        default="",
        description="The section's website URL (http/https) as it appears on the page. Empty if absent.",
    )
    meetings: list[Meeting] = Field(
        default_factory=list,
        description=(
            "Every meeting listed for this section, one entry per meeting, "
            "in the order shown on the page (e.g. a Fall 2026 entry and a "
            "Spring 2027 entry)."
        ),
    )

    @field_validator("section", "section_url", mode="before")
    @classmethod
    def _normalize_text(cls, value):
        return Meeting._normalize_text(value)
