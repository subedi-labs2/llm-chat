import asyncio
from collections.abc import Callable
from datetime import date

import httpx
import pytest

from src.core.config import Settings
from src.recalls.client import RecallClient, RecallSourceError

Handler = Callable[[httpx.Request], httpx.Response]

NHTSA_RECALL = {
    "Manufacturer": "Honda (American Honda Motor Co.)",
    "NHTSACampaignNumber": "18V268000",
    "parkIt": False,
    "parkOutSide": True,
    "overTheAirUpdate": False,
    "ReportReceivedDate": "26/04/2018",
    "Component": "ELECTRICAL SYSTEM",
    "Summary": "The wiring may short.",
    "Consequence": "Increased risk of fire.",
    "Remedy": "Dealers will replace the harness.",
    "Notes": "Owners may contact Honda.",
    "ModelYear": "2018",
    "Make": "HONDA",
    "Model": "ACCORD",
}


def cpsc_recall(number: str, recall_date: str) -> dict[str, object]:
    return {
        "RecallNumber": number,
        "RecallDate": f"{recall_date}T00:00:00",
        "Title": f"Stroller recall {number}",
        "Description": "The frame can break.",
        "URL": f"https://www.cpsc.gov/Recalls/{number}",
        "ConsumerContact": "Call 800-000-0000",
        "Products": [{"Name": "Stroller", "NumberOfUnits": "About 1,000"}],
        "Hazards": [{"Name": "Fall hazard"}],
        "Remedies": [{"Name": "Refund"}],
        "RemedyOptions": [{"Option": "Refund"}],
        "Manufacturers": [{"Name": "Acme"}],
        "Retailers": [{"Name": "Big Store"}],
    }


def run_with(handler: Handler, call: Callable[[RecallClient], object], **settings: object):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await call(RecallClient(http, Settings(**settings)))  # type: ignore[misc]

    return asyncio.run(go())


def test_search_vehicle_recalls_parses_nhtsa_response() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Count": 1, "results": [NHTSA_RECALL]})

    results = run_with(handler, lambda c: c.search_vehicle_recalls("Honda", "Accord", 2018))

    assert seen[0].url.path == "/recalls/recallsByVehicle"
    assert dict(seen[0].url.params) == {"make": "Honda", "model": "Accord", "modelYear": "2018"}
    assert results.total_found == 1
    recall = results.recalls[0]
    assert recall.campaign_number == "18V268000"
    assert recall.park_outside is True
    assert recall.url == "https://www.nhtsa.gov/recalls?nhtsaId=18V268000"


def test_search_vehicle_recalls_treats_nhtsa_400_with_results_as_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"Count": 0, "results": []})

    results = run_with(handler, lambda c: c.search_vehicle_recalls("Honda", "Nope", 2018))

    assert results.total_found == 0
    assert results.recalls == []


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, text="oops"), httpx.Response(200, text="<html>")],
)
def test_search_vehicle_recalls_raises_on_bad_response(response: httpx.Response) -> None:
    with pytest.raises(RecallSourceError):
        run_with(lambda _: response, lambda c: c.search_vehicle_recalls("Honda", "Accord", 2018))


def test_network_errors_raise_recall_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(RecallSourceError):
        run_with(handler, lambda c: c.decode_vin("1HGCV1F30JA000001"))


def test_decode_vin() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/vehicles/DecodeVinValues/1HGCV1F30JA000001"
        row = {"Make": "HONDA", "Model": "Accord", "ModelYear": "2018", "ErrorCode": "0"}
        return httpx.Response(200, json={"Results": [row]})

    vehicle = run_with(handler, lambda c: c.decode_vin("1HGCV1F30JA000001"))

    assert (vehicle.make, vehicle.model, vehicle.model_year) == ("HONDA", "Accord", 2018)
    assert vehicle.decode_warning is None


def test_search_product_recalls_sorts_newest_first_and_limits() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        rows = [cpsc_recall("24001", "2024-01-05"), cpsc_recall("25001", "2025-03-01")]
        rows.append(cpsc_recall("23001", "2023-06-01"))
        return httpx.Response(200, json=rows)

    results = run_with(
        handler,
        lambda c: c.search_product_recalls(
            product_name="stroller", recall_date_start=date(2023, 1, 1)
        ),
        max_product_recall_results=2,
    )

    assert dict(seen[0].url.params) == {
        "format": "json",
        "ProductName": "stroller",
        "RecallDateStart": "2023-01-01",
    }
    assert (results.total_found, results.returned) == (3, 2)
    assert [r.recall_number for r in results.recalls] == ["25001", "24001"]
    first = results.recalls[0]
    assert first.recall_date == "2025-03-01"
    assert first.hazards == ["Fall hazard"]
    assert first.number_of_units == ["About 1,000"]
