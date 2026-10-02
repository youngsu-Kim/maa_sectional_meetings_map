from pydantic import BaseModel, Field, field_validator


class SectionMeeting(BaseModel):
    """One MAA section's meeting entry, extracted from the section-meetings page."""

    @field_validator(
        "section", "date", "location", "speakers", "section_url",
        mode="before",
    )
    @classmethod
    def _normalize_text(cls, value):
        # The MAA page contains &nbsp; entities that surface as \xa0 in
        # extracted text, breaking cache lookups and geocoding queries.
        if isinstance(value, str):
            return " ".join(value.replace("\xa0", " ").split())
        return value


    row_id: str = Field(
        description="Row identifier from the page HTML, e.g. 'row-0'. Use the exact value provided."
    )
    section: str = Field(
        description="MAA section name, exactly as provided."
    )
    date: str = Field(
        default="",
        description=(
            "Meeting date(s) exactly as shown on the page. Multiple adjacent dates "
            "stay together in this one field. A date without a year uses the year "
            "listed in the HTML. Empty if not announced."
        ),
    )
    location: str = Field(
        default="",
        description="Venue and city/state of the meeting. Empty if not announced.",
    )
    speakers: str = Field(
        default="",
        description=(
            "All speaker names together in this one field, comma separated. "
            "Empty if not announced."
        ),
    )
    section_url: str = Field(
        default="",
        description="The section's website URL (http/https) as it appears on the page. Empty if absent.",
    )
