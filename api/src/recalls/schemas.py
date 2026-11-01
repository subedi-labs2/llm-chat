from typing import Literal

from pydantic import BaseModel

Agency = Literal["NHTSA", "CPSC"]


class DecodedVehicle(BaseModel):
    vin: str
    make: str | None
    model: str | None
    model_year: int | None
    decode_warning: str | None = None


class VehicleRecall(BaseModel):
    campaign_number: str
    manufacturer: str
    make: str
    model: str
    model_year: str
    component: str
    summary: str
    consequence: str
    remedy: str
    notes: str
    report_received_date: str
    park_it: bool
    park_outside: bool
    over_the_air_update: bool
    url: str


class VehicleRecallResults(BaseModel):
    make: str
    model: str
    model_year: int
    total_found: int
    recalls: list[VehicleRecall]


class ProductRecall(BaseModel):
    recall_number: str
    recall_date: str
    title: str
    description: str
    products: list[str]
    hazards: list[str]
    remedies: list[str]
    remedy_options: list[str]
    manufacturers: list[str]
    retailers: list[str]
    number_of_units: list[str]
    consumer_contact: str
    url: str


class ProductRecallResults(BaseModel):
    total_found: int
    returned: int
    recalls: list[ProductRecall]


class SourceUnavailable(BaseModel):
    agency: Agency
    error: str
