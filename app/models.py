"""SQLAlchemy ORM models for the moto-maintenance database.

A `Bike` owns its `rides`, `hours_events`, and `service_records`: deleting a
bike must delete all of them too, with no orphaned rows and no foreign-key
error. Those three relationships are configured with
`cascade="all, delete-orphan"` so an ORM-level `session.delete(bike)` removes
the children in the same transaction. This relies on deletes always going
through the ORM (not raw SQL), so there is no DB-level `ON DELETE CASCADE`.

Date fields are stored as ISO-format strings (`String` columns) rather than
SQLAlchemy's `Date` type: SQLite's `Date` type rejects plain `str` input, but
every caller constructs these models with date strings (e.g. "2026-01-01")
rather than `date` objects, so `Mapped[date]` here documents the intended
value shape while `String` is the lenient on-disk representation that
matches how the rest of the app calls these constructors.
"""

from datetime import date, datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bike(Base):
    __tablename__ = "bikes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str]
    model_key: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    rides: Mapped[list["Ride"]] = relationship(
        back_populates="bike", cascade="all, delete-orphan"
    )
    hours_events: Mapped[list["HoursEvent"]] = relationship(
        back_populates="bike", cascade="all, delete-orphan"
    )
    service_records: Mapped[list["ServiceRecord"]] = relationship(
        back_populates="bike", cascade="all, delete-orphan"
    )


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    date: Mapped[date] = mapped_column(String)
    hours: Mapped[float]
    notes: Mapped[str | None] = mapped_column(default=None)
    fork_compression: Mapped[int | None] = mapped_column(default=None)
    fork_rebound: Mapped[int | None] = mapped_column(default=None)
    shock_lsc: Mapped[int | None] = mapped_column(default=None)
    shock_hsc: Mapped[float | None] = mapped_column(default=None)
    shock_rebound: Mapped[int | None] = mapped_column(default=None)
    sag_static: Mapped[int | None] = mapped_column(default=None)
    sag_rider: Mapped[int | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="rides")


class HoursEvent(Base):
    __tablename__ = "hours_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    date: Mapped[date] = mapped_column(String)
    kind: Mapped[str]
    hours: Mapped[float]
    ride_id: Mapped[int | None] = mapped_column(default=None)
    note: Mapped[str | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="hours_events")


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    item_key: Mapped[str]
    service_point: Mapped[int]
    completed_date: Mapped[date] = mapped_column(String)
    engine_hours: Mapped[float]
    notes: Mapped[str | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="service_records")
