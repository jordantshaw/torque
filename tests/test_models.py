from sqlalchemy import inspect

from app.db import get_engine, init_db, get_sessionmaker
from app.models import Bike, Ride, HoursEvent, ServiceRecord


def test_init_db_creates_all_tables():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    names = set(inspect(engine).get_table_names())
    assert {"bikes", "rides", "hours_events", "service_records"} <= names


def test_deleting_bike_cascades_children():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    Session = get_sessionmaker(engine)
    with Session() as session:
        bike = Bike(nickname="Race Bike", model_key="beta-300-rr-race-2026")
        session.add(bike)
        session.flush()
        ride = Ride(bike_id=bike.id, date="2026-01-01", hours=3)
        session.add(ride)
        session.flush()
        session.add(HoursEvent(bike_id=bike.id, date="2026-01-01", kind="ride", hours=3, ride_id=ride.id))
        session.add(ServiceRecord(bike_id=bike.id, item_key="oil", service_point=30, completed_date="2026-01-01", engine_hours=30))
        session.commit()

        session.delete(bike)
        session.commit()

        assert session.query(Ride).count() == 0
        assert session.query(HoursEvent).count() == 0
        assert session.query(ServiceRecord).count() == 0
