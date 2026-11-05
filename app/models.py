"""SQLAlchemy ORM models for the Torque database.

A `Bike` owns its `rides`, `hours_events`, `service_records`,
`carb_settings` and `unplanned_jobs` (which own their `items`): deleting a
bike must delete all of them too, with no orphaned rows and no foreign-key
error. Those relationships are configured with
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
    # km or mi; only used when the bike's model is distance-based.
    distance_unit: Mapped[str] = mapped_column(default="km", server_default="km")
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
    carb_settings: Mapped[list["CarbSetting"]] = relationship(
        back_populates="bike", cascade="all, delete-orphan"
    )
    unplanned_jobs: Mapped[list["UnplannedJob"]] = relationship(
        back_populates="bike", cascade="all, delete-orphan"
    )


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    date: Mapped[date] = mapped_column(String)
    hours: Mapped[float]
    notes: Mapped[str | None] = mapped_column(default=None)
    location: Mapped[str | None] = mapped_column(default=None)
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
    # Set when this point was recorded by counting an unplanned job.
    unplanned_job_id: Mapped[int | None] = mapped_column(default=None)
    # Set when this point was caught up by completing a later point (that point).
    covered_by_point: Mapped[int | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="service_records")


class UnplannedJob(Base):
    """Maintenance done off-schedule, covering zero or more scheduled items."""

    __tablename__ = "unplanned_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    date: Mapped[date] = mapped_column(String)
    engine_hours: Mapped[float]
    note: Mapped[str | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="unplanned_jobs")
    items: Mapped[list["UnplannedJobItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="UnplannedJobItem.id"
    )

    @property
    def item_keys(self) -> list[str]:
        return [item.item_key for item in self.items]


class UnplannedJobItem(Base):
    __tablename__ = "unplanned_job_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("unplanned_jobs.id"))
    item_key: Mapped[str]

    job: Mapped["UnplannedJob"] = relationship(back_populates="items")


class CarbSetting(Base):
    __tablename__ = "carb_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"))
    date: Mapped[date] = mapped_column(String)
    main_jet: Mapped[str] = mapped_column(default="")
    needle: Mapped[str] = mapped_column(default="")
    needle_position: Mapped[str] = mapped_column(default="")
    pilot_jet: Mapped[str] = mapped_column(default="")
    air_screw: Mapped[str] = mapped_column(default="")
    note: Mapped[str | None] = mapped_column(default=None)
    # Set when the entry was logged as part of a ride (at most one per ride).
    ride_id: Mapped[int | None] = mapped_column(default=None)

    bike: Mapped["Bike"] = relationship(back_populates="carb_settings")
