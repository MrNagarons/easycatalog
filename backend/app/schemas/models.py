from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceName(str, Enum):
    kaspi = "kaspi"
    wildberries = "wildberries"
    ozon = "ozon"


class ProductCard(BaseModel):
    source: SourceName
    title: str
    image_url: str | None = None
    price: str | None = None
    product_url: str
    rating: str | None = None
    reviews_count: str | None = None
    seller: str | None = None


class ProductDetail(BaseModel):
    source: SourceName
    title: str
    product_url: str
    image_url: str | None = None
    price: str | None = None
    rating: str | None = None
    reviews_count: str | None = None
    description: str | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)
    raw_sections: dict[str, list[str]] = Field(default_factory=dict)


class SourceResult(BaseModel):
    source: SourceName
    items: list[ProductCard] = Field(default_factory=list)
    error: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SourceResult]


class ProxyConfigPayload(BaseModel):
    proxies_text: str


class ProxyTogglePayload(BaseModel):
    enabled: bool


class ProxyRecord(BaseModel):
    raw: str
    url: str | None


class ProxyStatus(BaseModel):
    enabled: bool
    total: int
    active: int
    dead: int
    current_index: int


class ProxyErrorEvent(BaseModel):
    proxy: str | None
    reason: str
    url: str | None = None
    occurred_at: datetime
