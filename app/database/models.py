"""ORM-модели, повторяющие схему MySQL из плана.

Связка карточки: Client + Property + Deal. История ведётся в AuditEvent.
Типы выбраны переносимыми, чтобы те же модели работали на локальной SQLite
для тестов и на MySQL в рабочей среде.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("agent_id", "phone", name="uq_clients_agent_phone"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    client_segment: Mapped[str] = mapped_column(String(1), default="C")
    lead_source: Mapped[str | None] = mapped_column(String(100))
    preferred_contact_channel: Mapped[str] = mapped_column(String(50), default="telegram")
    preferred_call_time: Mapped[str | None] = mapped_column(Text)
    tax_status: Mapped[str] = mapped_column(String(50), default="individual")
    resident_status: Mapped[bool] = mapped_column(Boolean, default=True)
    under_bankruptcy_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    agency_contract_number: Mapped[str | None] = mapped_column(String(100))
    agency_contract_date: Mapped[date | None] = mapped_column(Date)
    commission_type: Mapped[str | None] = mapped_column(String(50))
    commission_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    consent_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    encrypted_pd_passport: Mapped[str | None] = mapped_column(String(255))
    encrypted_pd_fullname: Mapped[str | None] = mapped_column(String(255))
    encrypted_pd_phone: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    deals: Mapped[list["Deal"]] = relationship(back_populates="client")


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    cadastral_number: Mapped[str | None] = mapped_column(String(50), unique=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(Text, nullable=False)
    house_number: Mapped[str] = mapped_column(String(20), nullable=False)
    apartment_number: Mapped[str | None] = mapped_column(String(10))
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    house_material: Mapped[str | None] = mapped_column(String(50))
    year_built: Mapped[int | None] = mapped_column(SmallInteger)
    floor: Mapped[int | None] = mapped_column(SmallInteger)
    total_floors: Mapped[int | None] = mapped_column(SmallInteger)
    total_area: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    living_area: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    kitchen_area: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rooms_count: Mapped[int | None] = mapped_column(SmallInteger)
    ceiling_height: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    bathroom_type: Mapped[str | None] = mapped_column(String(50))
    balcony_loggia: Mapped[str | None] = mapped_column(String(50))
    window_view: Mapped[str | None] = mapped_column(String(100))
    repair_type: Mapped[str | None] = mapped_column(String(50))
    has_furniture: Mapped[bool] = mapped_column(Boolean, default=False)
    has_appliances: Mapped[bool] = mapped_column(Boolean, default=False)
    ownership_type: Mapped[str | None] = mapped_column(String(100))
    owners_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    has_minor_owners: Mapped[bool] = mapped_column(Boolean, default=False)
    encumbrances: Mapped[str | None] = mapped_column(Text)
    bank_mortgage_name: Mapped[str | None] = mapped_column(String(100))
    readiness_for_deal: Mapped[str | None] = mapped_column(String(50))
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Секретное поле: не попадает в DOCX и не передаётся в LLM.
    min_acceptable_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    keys_at_agency: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    deals: Mapped[list["Deal"]] = relationship(back_populates="property")


class ClientProperty(Base):
    __tablename__ = "client_properties"

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True
    )
    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    deal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new")
    offer_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="deals")
    property: Mapped["Property"] = relationship(back_populates="deals")


class Demand(Base):
    __tablename__ = "demands"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    cities: Mapped[list] = mapped_column(JSON, nullable=False)
    districts: Mapped[list | None] = mapped_column(JSON)
    streets: Mapped[list | None] = mapped_column(JSON)
    distance_to_metro_min: Mapped[int | None] = mapped_column(SmallInteger)
    rooms_desired: Mapped[list | None] = mapped_column(JSON)
    min_area: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    max_area: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    preferred_floors: Mapped[list | None] = mapped_column(JSON)
    kitchen_area_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    repair_preferences: Mapped[list | None] = mapped_column(JSON)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    funding_source: Mapped[str | None] = mapped_column(String(50))
    mortgage_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_bank_name: Mapped[str | None] = mapped_column(String(100))
    down_payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    buying_reason: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str | None] = mapped_column(String(50))
    raw_wishes_text: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="SET NULL")
    )
    property_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="SET NULL")
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    call_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    audio_file_url: Mapped[str | None] = mapped_column(String(255))
    call_sentiment: Mapped[str | None] = mapped_column(String(20))
    showing_sheet_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    showing_duration_min: Mapped[int | None] = mapped_column(SmallInteger)
    who_attended: Mapped[list | None] = mapped_column(JSON)
    buyer_feedback: Mapped[str | None] = mapped_column(Text)
    seller_feedback: Mapped[str | None] = mapped_column(Text)
    proposed_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    seller_counter_offer: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    discount_agreed: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_platforms: Mapped[list | None] = mapped_column(JSON)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    leads_generated_count: Mapped[int] = mapped_column(Integer, default=0)
    summarized_action: Mapped[str] = mapped_column(Text, nullable=False)
    next_action_agreed: Mapped[str | None] = mapped_column(Text)
    next_action_deadline: Mapped[datetime | None] = mapped_column(DateTime)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="SET NULL")
    )
    property_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    initiator_type: Mapped[str] = mapped_column(String(20), nullable=False)
    initiator_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    changes_json: Mapped[dict | None] = mapped_column(JSON)
    source_text: Mapped[str | None] = mapped_column(Text)
    source_audio_file_id: Mapped[str | None] = mapped_column(String(255))
    transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
