from sqlalchemy import inspect

from app.db import get_engine, init_db, get_sessionmaker
from app.models import Bike, CarbSetting, Ride, HoursEvent, ServiceRecord


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


def test_deleting_a_bike_deletes_its_carb_settings():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    Session = get_sessionmaker(engine)
    with Session() as session:
        bike = Bike(nickname="Race Bike", model_key="beta-300-rr-race-2026")
        session.add(bike)
        session.flush()
        session.add(CarbSetting(bike_id=bike.id, date="2026-01-01", main_jet="175"))
        session.add(CarbSetting(bike_id=bike.id, date="2026-02-01", main_jet="172"))
        session.commit()
        assert session.query(CarbSetting).count() == 2

        session.delete(bike)
        session.commit()

        assert session.query(CarbSetting).count() == 0


def test_existing_database_gains_ride_location_and_carb_ride_id_columns(tmp_path):
    from sqlalchemy import inspect, text

    engine = get_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE rides (id INTEGER PRIMARY KEY, bike_id INTEGER, date VARCHAR, hours FLOAT)"
        ))
        conn.execute(text(
            "CREATE TABLE carb_settings (id INTEGER PRIMARY KEY, bike_id INTEGER, date VARCHAR)"
        ))
    init_db(engine)
    assert "location" in {c["name"] for c in inspect(engine).get_columns("rides")}
    assert "ride_id" in {c["name"] for c in inspect(engine).get_columns("carb_settings")}


def test_deleting_bike_deletes_unplanned_jobs_and_items():
    from app.models import UnplannedJob, UnplannedJobItem

    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    Session = get_sessionmaker(engine)
    with Session() as session:
        bike = Bike(nickname="Race Bike", model_key="test-bike")
        session.add(bike)
        session.flush()
        job = UnplannedJob(bike_id=bike.id, date="2026-11-02", engine_hours=25, note="Bent radiators")
        job.items.append(UnplannedJobItem(item_key="oil"))
        session.add(job)
        session.commit()
        assert session.query(UnplannedJob).one().item_keys == ["oil"]

        session.delete(bike)
        session.commit()

        assert session.query(UnplannedJob).count() == 0
        assert session.query(UnplannedJobItem).count() == 0


def test_existing_database_gains_service_record_columns(tmp_path):
    from sqlalchemy import inspect, text

    engine = get_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE service_records (id INTEGER PRIMARY KEY, bike_id INTEGER, item_key VARCHAR, "
            "service_point INTEGER, completed_date VARCHAR, engine_hours FLOAT, notes VARCHAR)"
        ))
    init_db(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("service_records")}
    assert {"unplanned_job_id", "covered_by_point"} <= columns
