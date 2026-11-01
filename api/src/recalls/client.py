from datetime import date
from typing import Any

import httpx

from src.core.config import Settings
from src.recalls.schemas import (
    DecodedVehicle,
    ProductRecall,
    ProductRecallResults,
    VehicleRecall,
    VehicleRecallResults,
)


class RecallSourceError(Exception):
    """A recall data source could not be reached or returned an unexpected response."""


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _names(items: Any, key: str = "Name") -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item.get(key)) for item in items if isinstance(item, dict) and item.get(key)]


class RecallClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def _get_json(self, url: str, params: dict[str, str], ok_statuses: set[int]) -> Any:
        try:
            response = await self._http.get(
                url, params=params, timeout=self._settings.recall_api_timeout_seconds
            )
        except httpx.HTTPError as exc:
            raise RecallSourceError(f"Request to {url} failed: {exc.__class__.__name__}") from exc
        if response.status_code not in ok_statuses:
            raise RecallSourceError(f"{url} returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise RecallSourceError(f"{url} returned invalid JSON") from exc

    async def decode_vin(self, vin: str) -> DecodedVehicle:
        url = f"{self._settings.vpic_api_url}/vehicles/DecodeVinValues/{vin}"
        data = await self._get_json(url, {"format": "json"}, {200})
        results = data.get("Results") if isinstance(data, dict) else None

        if not isinstance(results, list) or not results:
            raise RecallSourceError("VIN decoder returned no results")
        
        row = results[0]
        if not isinstance(row, dict):
            raise RecallSourceError("VIN decoder returned an invalid result")
        
        year = _text(row.get("ModelYear"))
        error_code = _text(row.get("ErrorCode"))
        return DecodedVehicle(
            vin=vin,
            make=_text(row.get("Make")) or None,
            model=_text(row.get("Model")) or None,
            model_year=int(year) if year.isdigit() else None,
            decode_warning=None if error_code == "0" else _text(row.get("ErrorText")) or None,
        )

    async def search_vehicle_recalls(
        self, make: str, model: str, model_year: int
    ) -> VehicleRecallResults:
        url = f"{self._settings.nhtsa_api_url}/recalls/recallsByVehicle"
        params = {"make": make, "model": model, "modelYear": str(model_year)}
        # NHTSA answers 400 (with an empty result set) for unknown make/model combinations.
        data = await self._get_json(url, params, {200, 400})
        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise RecallSourceError("NHTSA returned an unexpected response")

        recalls = [
            VehicleRecall(
                campaign_number=_text(row.get("NHTSACampaignNumber")),
                manufacturer=_text(row.get("Manufacturer")),
                make=_text(row.get("Make")),
                model=_text(row.get("Model")),
                model_year=_text(row.get("ModelYear")),
                component=_text(row.get("Component")),
                summary=_text(row.get("Summary")),
                consequence=_text(row.get("Consequence")),
                remedy=_text(row.get("Remedy")),
                notes=_text(row.get("Notes")),
                report_received_date=_text(row.get("ReportReceivedDate")),
                park_it=bool(row.get("parkIt")),
                park_outside=bool(row.get("parkOutSide")),
                over_the_air_update=bool(row.get("overTheAirUpdate")),
                url=f"https://www.nhtsa.gov/recalls?nhtsaId={_text(row.get('NHTSACampaignNumber'))}",
            )
            for row in rows
            if isinstance(row, dict) and row.get("NHTSACampaignNumber")
        ]
        return VehicleRecallResults(
            make=make, model=model, model_year=model_year, total_found=len(recalls), recalls=recalls
        )

    async def search_product_recalls(
        self,
        *,
        product_name: str | None = None,
        manufacturer: str | None = None,
        recall_number: str | None = None,
        recall_date_start: date | None = None,
    ) -> ProductRecallResults:
        params = {
            key: value
            for key, value in {
                "format": "json",
                "ProductName": product_name,
                "Manufacturer": manufacturer,
                "RecallNumber": recall_number,
                "RecallDateStart": recall_date_start.isoformat() if recall_date_start else None,
            }.items()
            if value
        }
        data = await self._get_json(f"{self._settings.cpsc_api_url}/Recall", params, {200})
        if not isinstance(data, list):
            raise RecallSourceError("CPSC returned an unexpected response")

        rows = sorted(
            (row for row in data if isinstance(row, dict)),
            key=lambda row: _text(row.get("RecallDate")),
            reverse=True,
        )
        limited = rows[: self._settings.max_product_recall_results]
        recalls = [
            ProductRecall(
                recall_number=_text(row.get("RecallNumber")),
                recall_date=_text(row.get("RecallDate"))[:10],
                title=_text(row.get("Title")),
                description=_text(row.get("Description")),
                products=_names(row.get("Products")),
                hazards=_names(row.get("Hazards")),
                remedies=_names(row.get("Remedies")),
                remedy_options=_names(row.get("RemedyOptions"), "Option"),
                manufacturers=_names(row.get("Manufacturers")),
                retailers=_names(row.get("Retailers")),
                number_of_units=_names(row.get("Products"), "NumberOfUnits"),
                consumer_contact=_text(row.get("ConsumerContact")),
                url=_text(row.get("URL")),
            )
            for row in limited
        ]
        return ProductRecallResults(total_found=len(rows), returned=len(recalls), recalls=recalls)
