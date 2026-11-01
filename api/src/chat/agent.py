import re
from dataclasses import dataclass, field
from datetime import date

import pydantic_ai
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

from src.chat.schemas import Source
from src.recalls.client import RecallClient, RecallSourceError
from src.recalls.schemas import (
    DecodedVehicle,
    ProductRecallResults,
    SourceUnavailable,
    VehicleRecallResults,
)

pydantic_ai.BANNER_ENABLED = False

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

INSTRUCTIONS = """\
You are a consumer product and vehicle safety assistant. You help people find official recall
information from NHTSA (motor vehicles) and the CPSC (consumer products). Today is {today}.

Grounding rules:
- State recall facts (campaign or recall numbers, dates, defects, risks, remedies, unit counts) only
  when they come from tool results in this conversation. Never answer recall questions from memory.
- If a tool reports that a source is unavailable, say you could not check that source right now.
  Do not guess.
- If a search finds nothing, say no recalls were found in that source for that search. Explain
  that this does not guarantee the item is safe or unaffected.

Vehicles:
- You need the make, model, and model year. If the user gives a VIN, call decode_vin first.
- If the make, model, or year is missing or ambiguous, ask for it (or the VIN) before searching.
- Make, model, and year results may include recalls that do not apply to every vehicle. Tell the
  user to confirm with their 17-character VIN at nhtsa.gov/recalls or with a dealer.
- List "park it" or "park outside" warnings first and clearly. These mean the vehicle should not
  be driven or should be parked away from structures.

Products:
- Search the CPSC with the most specific details the user gave: product name, brand or
  manufacturer, model, or recall number. If the results look unrelated or there are many, say so
  and ask for the brand or model.
- If more results were found than returned, mention that and suggest narrowing the search.

Answer format:
- Plain text with short paragraphs and "-" bullets. No markdown headings, tables, or bold text.
- For each recall, include its number, the problem, the risk, and the remedy.
- Put the campaign or recall number of every recall you mention in cited_recall_ids.
- Decline questions that are not about product or vehicle safety.
- If someone has been injured or is in danger, tell them to contact emergency services.
"""


class ChatAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000, description="The reply shown to the user.")
    cited_recall_ids: list[str] = Field(
        default_factory=list,
        description="NHTSA campaign numbers or CPSC recall numbers mentioned in the answer.",
    )


@dataclass
class ChatDeps:
    recalls: RecallClient
    sources: dict[str, Source] = field(default_factory=dict)


recall_agent = Agent(
    deps_type=ChatDeps,
    output_type=ChatAnswer,
    instructions=lambda _: INSTRUCTIONS.format(today=date.today().isoformat()),
    retries=2,
)


@recall_agent.tool
async def decode_vin(ctx: RunContext[ChatDeps], vin: str) -> DecodedVehicle | SourceUnavailable:
    """Decode a 17-character VIN into make, model, and model year using NHTSA vPIC."""
    normalized = vin.strip().upper()
    if not VIN_PATTERN.fullmatch(normalized):
        raise ModelRetry(
            "A VIN has 17 letters and digits and never contains I, O, or Q. "
            "Ask the user to double-check it."
        )
    try:
        return await ctx.deps.recalls.decode_vin(normalized)
    except RecallSourceError as exc:
        return SourceUnavailable(agency="NHTSA", error=str(exc))


@recall_agent.tool
async def search_vehicle_recalls(
    ctx: RunContext[ChatDeps], make: str, model: str, model_year: int
) -> VehicleRecallResults | SourceUnavailable:
    """Search NHTSA for recalls on a vehicle by make, model, and model year.

    Args:
        make: Vehicle make, for example "Honda".
        model: Vehicle model, for example "Accord".
        model_year: Four-digit model year.
    """
    if not 1949 <= model_year <= date.today().year + 2:
        raise ModelRetry("model_year must be a realistic four-digit year.")
    try:
        results = await ctx.deps.recalls.search_vehicle_recalls(
            make.strip(), model.strip(), model_year
        )
    except RecallSourceError as exc:
        return SourceUnavailable(agency="NHTSA", error=str(exc))
    for recall in results.recalls:
        ctx.deps.sources[recall.campaign_number] = Source(
            id=recall.campaign_number,
            agency="NHTSA",
            title=f"{recall.model_year} {recall.make} {recall.model}: {recall.component}",
            url=recall.url,
        )
    return results


@recall_agent.tool
async def search_product_recalls(
    ctx: RunContext[ChatDeps],
    product_name: str | None = None,
    manufacturer: str | None = None,
    recall_number: str | None = None,
    recall_date_start: date | None = None,
) -> ProductRecallResults | SourceUnavailable:
    """Search CPSC consumer product recalls. Results are sorted newest first.

    Args:
        product_name: Product name keywords, for example "stroller" or "space heater".
        manufacturer: Brand or manufacturer name.
        recall_number: CPSC recall number, if known.
        recall_date_start: Only return recalls announced on or after this date.
    """
    if not any([product_name, manufacturer, recall_number]):
        raise ModelRetry("Provide at least one of product_name, manufacturer, or recall_number.")
    try:
        results = await ctx.deps.recalls.search_product_recalls(
            product_name=product_name,
            manufacturer=manufacturer,
            recall_number=recall_number,
            recall_date_start=recall_date_start,
        )
    except RecallSourceError as exc:
        return SourceUnavailable(agency="CPSC", error=str(exc))
    for recall in results.recalls:
        if recall.recall_number and recall.url:
            ctx.deps.sources[recall.recall_number] = Source(
                id=recall.recall_number, agency="CPSC", title=recall.title, url=recall.url
            )
    return results
