"""
SQL database layer (SQLAlchemy) — works with SQLite, MS SQL Server, PostgreSQL, MySQL.

Tables
  hospitals             one row per hospital (capacity columns live here)
  hospital_specialties  hospital_id, specialty, on_duty, doctor
  hospital_equipment    hospital_id, equipment
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import (Boolean, Column, Float, ForeignKey, Index, Integer, MetaData, String, Table, Unicode,
                        create_engine, func, insert, select)
from sqlalchemy.engine import Engine

from . import config

metadata = MetaData()

hospitals = Table(
    "hospitals", metadata,
    Column("id", String(10), primary_key=True),
    Column("name", Unicode(200), nullable=False),
    Column("area", Unicode(120)),
    Column("city", Unicode(80)),
    Column("phone", String(30)),
    Column("lat", Float, nullable=False),
    Column("lng", Float, nullable=False),
    Column("tier", String(10), nullable=False),          # low / medium / high
    Column("cost", Unicode(80)),
    Column("rating", Float),
    Column("emergency_24x7", Boolean, nullable=False, default=True),
    Column("icu_total", Integer, default=0),
    Column("icu_available", Integer, default=0),
    Column("ventilators_available", Integer, default=0),
    Column("ot_total", Integer, default=0),
    Column("ot_available", Integer, default=0),
    Column("general_beds_available", Integer, default=0),
    Column("ambulances_available", Integer, default=0),
    Column("als_ambulance", Boolean, default=False),
    Column("accepts_ayushman_bharat", Boolean, default=False),
    Column("updated_at", String(40)),
    Index("ix_hosp_tier_er", "tier", "emergency_24x7"),
)

hospital_specialties = Table(
    "hospital_specialties", metadata,
    Column("hospital_id", String(10), ForeignKey("hospitals.id", ondelete="CASCADE"), primary_key=True),
    Column("specialty", String(40), primary_key=True),
    Column("on_duty", Boolean, nullable=False, default=False),
    Column("doctor", Unicode(80)),
    Index("ix_spec_specialty", "specialty"),
)

hospital_equipment = Table(
    "hospital_equipment", metadata,
    Column("hospital_id", String(10), ForeignKey("hospitals.id", ondelete="CASCADE"), primary_key=True),
    Column("equipment", String(40), primary_key=True),
    Index("ix_equip_equipment", "equipment"),
)


@lru_cache
def get_engine() -> Engine:
    kwargs = {"pool_pre_ping": True}
    if config.DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(config.DATABASE_URL, **kwargs)


def create_tables(engine: Engine | None = None) -> None:
    metadata.create_all(engine or get_engine())


def load_seed(engine: Engine | None = None, seed_path: Path | None = None, replace: bool = True) -> int:
    """Insert seed/hospitals.json. replace=True wipes existing rows first."""
    engine = engine or get_engine()
    seed_path = seed_path or config.BACKEND_DIR / "seed" / "hospitals.json"
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    create_tables(engine)
    with engine.begin() as conn:
        if replace:
            conn.execute(hospital_equipment.delete())
            conn.execute(hospital_specialties.delete())
            conn.execute(hospitals.delete())
        h_rows, s_rows, e_rows = [], [], []
        for h in data:
            lng, lat = h["location"]["coordinates"]
            cap, amb = h["capacity"], h["ambulance"]
            h_rows.append({
                "id": h["_id"], "name": h["name"], "area": h["area"], "city": h.get("city"), "phone": h.get("phone"),
                "lat": lat, "lng": lng, "tier": h["tier"], "cost": h.get("cost"), "rating": h.get("rating"),
                "emergency_24x7": h["emergency_24x7"],
                "icu_total": cap["icu_total"], "icu_available": cap["icu_available"],
                "ventilators_available": cap["ventilators_available"],
                "ot_total": cap["ot_total"], "ot_available": cap["ot_available"],
                "general_beds_available": cap["general_beds_available"],
                "ambulances_available": amb["available"], "als_ambulance": amb["als"],
                "accepts_ayushman_bharat": h.get("accepts_ayushman_bharat", False),
                "updated_at": h.get("updated_at"),
            })
            duty = {d["specialty"]: d["doctor"] for d in h.get("specialists_on_duty", [])}
            s_rows += [{"hospital_id": h["_id"], "specialty": s, "on_duty": s in duty, "doctor": duty.get(s)}
                       for s in h["specialties"]]
            e_rows += [{"hospital_id": h["_id"], "equipment": e} for e in h["equipment"]]
        conn.execute(insert(hospitals), h_rows)
        conn.execute(insert(hospital_specialties), s_rows)
        conn.execute(insert(hospital_equipment), e_rows)
    return len(h_rows)


def seed_if_empty() -> None:
    """First run convenience: create tables and load demo data if the hospitals table is empty."""
    engine = get_engine()
    create_tables(engine)
    with engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(hospitals)).scalar_one()
    if count == 0:
        load_seed(engine, replace=False)
