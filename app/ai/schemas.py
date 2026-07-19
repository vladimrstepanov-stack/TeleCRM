"""Pydantic-контракт ответа LLM.

Схема строгая (`extra="forbid"`): любое неизвестное поле от модели считается
ошибкой и отклоняется до записи в БД. Так мы защищаемся от «фантазий» модели
и от попыток prompt-injection подсунуть произвольные данные.
"""

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Intent(str, Enum):
    UPSERT_DATA = "upsert_data"
    FETCH_DATA = "fetch_data"


class PropertyStatus(str, Enum):
    ACTIVE = "active"
    RESERVED = "reserved"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"


class DealType(str, Enum):
    BUY = "buy"
    SELL = "sell"


class DealStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    OFFER = "offer"
    DEPOSIT = "deposit"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RelationType(str, Enum):
    OWNER = "owner"
    BUYER = "buyer"


class ActivityType(str, Enum):
    NOTE = "note"
    CALL = "call"
    SHOWING = "showing"
    NEGOTIATION = "negotiation"
    OFFER = "offer"
    STATUS_CHANGE = "status_change"
    PRICE_CHANGE = "price_change"


class Urgency(str, Enum):
    HOT = "hot"
    MEDIUM = "medium"
    COLD = "cold"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientData(_Strict):
    name: str | None = None
    phone: str | None = None
    client_segment: str | None = Field(default=None, max_length=1)
    lead_source: str | None = None


class PropertyData(_Strict):
    city: str | None = None
    district: str | None = None
    address: str | None = None
    house_number: str | None = None
    apartment_number: str | None = None
    property_type: str | None = None
    rooms_count: int | None = Field(default=None, ge=0, le=50)
    floor: int | None = Field(default=None, ge=-5, le=200)
    total_floors: int | None = Field(default=None, ge=0, le=200)
    total_area: Decimal | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0)
    status: PropertyStatus | None = None


class DealData(_Strict):
    deal_type: DealType | None = None
    status: DealStatus | None = None
    offer_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class ActivityData(_Strict):
    activity_type: ActivityType
    summarized_action: str
    buyer_feedback: str | None = None
    seller_feedback: str | None = None
    proposed_price: Decimal | None = Field(default=None, ge=0)
    next_action_agreed: str | None = None


class DemandData(_Strict):
    """Потребности покупателя: что клиент хочет купить."""

    rooms_desired: list[int] | None = None
    min_area: Decimal | None = Field(default=None, ge=0)
    max_area: Decimal | None = Field(default=None, ge=0)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    cities: list[str] | None = None


class SearchCriteria(_Strict):
    phone: str | None = None
    client_name: str | None = None
    address: str | None = None
    city: str | None = None


class LLMResult(_Strict):
    """Единый разобранный результат интерпретации сообщения."""

    intent: Intent
    client: ClientData | None = None
    property: PropertyData | None = None
    deal: DealData | None = None
    demand: DemandData | None = None
    activities: list[ActivityData] = Field(default_factory=list)
    search: SearchCriteria | None = None
