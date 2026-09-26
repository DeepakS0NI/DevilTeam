"""
CareShift AI — RAG backend (Gemini + SQL).
Run (from backend/):   uvicorn app.main:app --reload --port 8000
Docs:                  http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from sqlalchemy import select, text, update

from .db import get_engine, hospital_equipment, hospital_specialties, hospitals, seed_if_empty
from .gemini_rag import understand_query, write_recommendation
from .search import search
from .taxonomy import AREAS, DEFAULT_AREA, EQUIPMENT, SPECIALTIES, TIERS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("careshift")

app = FastAPI(title="CareShift AI – RAG Hospital Search", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    try:
        seed_if_empty()  # creates tables + loads demo data on first run
        log.info("Database ready (%s). Gemini: %s", config.DATABASE_URL.split("@")[-1],
                 "ON" if config.GEMINI_API_KEY else "OFF (keyword fallback)")
    except Exception as e:
        log.error("Database not reachable at startup: %s", e)


def vocabulary(conn) -> tuple[list[str], list[str]]:
    """Retrieval step for the prompt: which tags actually exist in the database right now."""
    db_specs = conn.execute(select(hospital_specialties.c.specialty).distinct()).scalars().all()
    db_equip = conn.execute(select(hospital_equipment.c.equipment).distinct()).scalars().all()
    specs = [s for s in SPECIALTIES if s in db_specs] or list(SPECIALTIES)
    equip = [e for e in EQUIPMENT if e in db_equip] or list(EQUIPMENT)
    return specs, equip


# ------------------------------------------------------------------ schemas

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, examples=["Papa ko 20 min se seene mein dard aur saans phool rahi hai"])
    area: str | None = Field(None, examples=["Hazratganj, Lucknow"])
    lat: float | None = None
    lng: float | None = None
    urgency: Literal["critical", "urgent", "soon"] | None = None
    tier: Literal["any", "low", "medium", "high"] = "any"
    limit: int = Field(4, ge=1, le=10)


class CapacityUpdate(BaseModel):
    icu_available: int | None = None
    ot_available: int | None = None
    ventilators_available: int | None = None
    general_beds_available: int | None = None


# ------------------------------------------------------------------ endpoints

@app.get("/api/health")
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "database": db_ok, "db_type": get_engine().dialect.name,
            "gemini": bool(config.GEMINI_API_KEY), "model": config.GEMINI_MODEL}


@app.post("/api/search")
def search_hospitals(req: SearchRequest):
    t0 = time.perf_counter()

    # Location: explicit lat/lng (browser GPS) > area dropdown > default
    if req.lat is not None and req.lng is not None:
        lat, lng = req.lat, req.lng
    else:
        key = (req.area or DEFAULT_AREA).split(",")[0].strip().lower()
        lat, lng = AREAS.get(key, AREAS[DEFAULT_AREA])

    try:
        with get_engine().connect() as conn:
            specs, equip = vocabulary(conn)
            plan = understand_query(req.query, req.urgency, specs, equip)            # 1. Gemini: text -> filter
            results, sql_used, note = search(conn, plan, lat, lng, req.tier, req.limit)  # 2. SQL retrieval + rank
    except HTTPException:
        raise
    except Exception as e:
        log.exception("search failed")
        raise HTTPException(503, f"Database unavailable: {e}")
    summary, recommendation_source = write_recommendation(req.query, plan, results)  # 3. Gemini: grounded answer

    return {
        "query": req.query,
        "plan": plan.model_dump(),
        "understood": [SPECIALTIES[s] for s in plan.specialties]
                      + [EQUIPMENT[e] for e in plan.equipment]
                      + (["ICU bed"] if plan.needs_icu else [])
                      + (["Free OT"] if plan.needs_ot else [])
                      + (["Ventilator"] if plan.needs_ventilator else []),
        "primary_label": SPECIALTIES[plan.specialties[0]] if plan.specialties else "General emergency",
        "sql": sql_used,
        "relaxed_note": note,
        "summary": summary,
        "recommendation_source": recommendation_source,
        "results": results,
        "count": len(results),
        "origin": {"lat": lat, "lng": lng},
        "took_ms": round((time.perf_counter() - t0) * 1000),
    }


@app.get("/api/hospitals")
def list_hospitals():
    """For the 'Our network' section."""
    with get_engine().connect() as conn:
        rows = conn.execute(select(hospitals).order_by(hospitals.c.name)).mappings().all()
        spec_map: dict[str, list[str]] = {}
        for r in conn.execute(select(hospital_specialties.c.hospital_id, hospital_specialties.c.specialty)):
            spec_map.setdefault(r.hospital_id, []).append(r.specialty)
    return [{"id": d["id"], "name": d["name"], "area": d["area"], "tier": d["tier"], "tier_label": TIERS[d["tier"]],
             "cost": d["cost"], "rating": d["rating"],
             "specialties": [SPECIALTIES.get(s, s) for s in sorted(spec_map.get(d["id"], []))],
             "icu": d["icu_available"]} for d in rows]


@app.get("/api/facilities")
def facilities():
    with get_engine().connect() as conn:
        specs, equip = vocabulary(conn)
    return {"specialties": {s: SPECIALTIES[s] for s in specs}, "equipment": {e: EQUIPMENT[e] for e in equip},
            "areas": list(AREAS), "tiers": TIERS}


@app.patch("/api/hospitals/{hospital_id}/capacity")
def update_capacity(hospital_id: str, body: CapacityUpdate):
    """Hospital staff / demo: update live bed counts."""
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "Nothing to update")
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    with get_engine().begin() as conn:
        res = conn.execute(update(hospitals).where(hospitals.c.id == hospital_id).values(**changes))
    if res.rowcount == 0:
        raise HTTPException(404, "Hospital not found")
    return {"ok": True, "updated": changes}
