"""Retrieval + ranking: turns a SearchPlan into a SQL query and scores the hospitals it returns."""
from __future__ import annotations

import math

from sqlalchemy import and_, exists, select
from sqlalchemy.engine import Connection

from .db import hospital_equipment as he, hospital_specialties as hs, hospitals as h
from .gemini_rag import SearchPlan
from .taxonomy import EQUIPMENT, SPECIALTIES, TIERS


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def build_filter(plan: SearchPlan, tier: str | None, level: int) -> list:
    """
    Returns a list of SQL WHERE conditions.
    level 0 = strict (everything the AI asked for)
    level 1 = drop equipment + capacity requirements (keep specialty)
    level 2 = any 24x7 emergency hospital
    """
    conds = [h.c.emergency_24x7 == True]  # noqa: E712  (renders "= 1", valid on SQL Server)
    if tier and tier != "any":
        conds.append(h.c.tier == tier)
    if level <= 1 and plan.specialties:
        conds.append(exists().where(hs.c.hospital_id == h.c.id, hs.c.specialty.in_(plan.specialties)))
    if level == 0:
        for eq in plan.equipment:  # hospital must have ALL requested equipment
            conds.append(exists().where(he.c.hospital_id == h.c.id, he.c.equipment == eq))
        if plan.needs_icu:
            conds.append(h.c.icu_available >= 1)
        if plan.needs_ventilator:
            conds.append(h.c.ventilators_available >= 1)
        if plan.needs_ot:
            conds.append(h.c.ot_available >= 1)
        if plan.needs_ambulance:
            conds.append(h.c.ambulances_available >= 1)
    return conds


def fetch_docs(conn: Connection, conds: list) -> tuple[list[dict], str]:
    """Runs the query and returns hospitals as nested dicts (+ the SQL text, for transparency in the UI)."""
    stmt = select(h).where(and_(*conds))
    rows = [dict(r._mapping) for r in conn.execute(stmt)]
    try:
        sql_text = str(stmt.compile(conn.engine, compile_kwargs={"literal_binds": True}))
    except Exception:
        sql_text = str(stmt)
    if not rows:
        return [], sql_text
    ids = [r["id"] for r in rows]
    specs: dict[str, list] = {i: [] for i in ids}
    for r in conn.execute(select(hs).where(hs.c.hospital_id.in_(ids))):
        specs[r.hospital_id].append(r)
    equip: dict[str, list] = {i: [] for i in ids}
    for r in conn.execute(select(he).where(he.c.hospital_id.in_(ids))):
        equip[r.hospital_id].append(r.equipment)

    docs = []
    for r in rows:
        docs.append({
            "_id": r["id"], "name": r["name"], "area": r["area"], "phone": r["phone"],
            "location": {"coordinates": [r["lng"], r["lat"]]},
            "tier": r["tier"], "cost": r["cost"], "rating": r["rating"],
            "specialties": sorted(s.specialty for s in specs[r["id"]]),
            "specialists_on_duty": [{"specialty": s.specialty, "doctor": s.doctor} for s in specs[r["id"]] if s.on_duty],
            "equipment": sorted(equip[r["id"]]),
            "capacity": {k: r[k] or 0 for k in ("icu_available", "ot_available", "ventilators_available")},
            "ambulance": {"available": r["ambulances_available"] or 0},
        })
    return docs, sql_text


RELAX_NOTES = {
    0: None,
    1: "No hospital had every requirement free right now — showing closest hospitals with the right specialty.",
    2: "No hospital with this specialty is available — showing nearest 24×7 emergency hospitals.",
}


def score_hospital(h: dict, plan: SearchPlan, lat: float, lng: float, max_km: float) -> dict:
    hlng, hlat = h["location"]["coordinates"]
    dist = haversine_km(lat, lng, hlat, hlng)
    cap = h["capacity"]
    on_duty = {d["specialty"]: d["doctor"] for d in h.get("specialists_on_duty", [])}

    # Specialty fit: first tag matters most. Full credit if specialist on duty, half if only the department exists.
    weights = [1.0, 0.6, 0.4][: len(plan.specialties)] or [1.0]
    spec_pts = 0.0
    matched = []
    for w, s in zip(weights, plan.specialties):
        if s in on_duty:
            spec_pts += w
            matched.append(s)
        elif s in h["specialties"]:
            spec_pts += w * 0.5
            matched.append(s)
    spec_fit = spec_pts / sum(weights) if plan.specialties else 0.5

    dist_fit = max(0.0, 1 - dist / max_km)

    icu_fit = min(cap["icu_available"] / 3, 1.0)
    ot_fit = min(cap["ot_available"] / 2, 1.0)
    vent_fit = min(cap["ventilators_available"] / 2, 1.0)
    need = [icu_fit] + ([ot_fit] if plan.needs_ot else []) + ([vent_fit] if plan.needs_ventilator else [])
    cap_fit = sum(need) / len(need)

    if plan.severity == "critical":  # closer matters more when every minute counts
        weights = {"specialty": 45, "distance": 32, "capacity": 23}
    else:
        weights = {"specialty": 50, "distance": 25, "capacity": 25}
    score_breakdown = {
        "specialty": round(weights["specialty"] * spec_fit, 1),
        "distance": round(weights["distance"] * dist_fit, 1),
        "capacity": round(weights["capacity"] * cap_fit, 1),
    }
    score = weights["specialty"] * spec_fit + weights["distance"] * dist_fit + weights["capacity"] * cap_fit

    specialist = next((f"{on_duty[s]} ({SPECIALTIES[s].split(' ')[0]})" for s in plan.specialties if s in on_duty), None)
    readiness = min(98, round(35 + min(cap["icu_available"], 8) * 4 + min(cap["ot_available"], 3) * 8
                              + (15 if specialist else 0)))

    if matched:
        reason = (f"Has <b>{', '.join(SPECIALTIES[s] for s in matched)}</b>"
                  f"{' with specialist on duty' if specialist else ' (specialist on call)'}; "
                  f"{cap['icu_available']} ICU bed(s), {cap['ot_available']} OT free, {dist:.1f} km away.")
    else:
        reason = f"No dedicated unit for this, but a 24×7 emergency with {cap['icu_available']} ICU bed(s), {dist:.1f} km away."

    return {
        "id": h["_id"], "name": h["name"], "area": h["area"], "phone": h.get("phone"),
        "tier": h["tier"], "tier_label": TIERS[h["tier"]], "cost": h.get("cost"), "rating": h.get("rating"),
        "lat": hlat, "lng": hlng,
        "distance_km": round(dist, 1), "eta_min": round(dist / 25 * 60) + 3,  # ~25 km/h city emergency speed
        "icu": cap["icu_available"], "ot": cap["ot_available"], "ventilators": cap["ventilators_available"],
        "ambulances": h.get("ambulance", {}).get("available", 0),
        "specialist": specialist,
        "matched_specialties": matched,
        "specialties": h["specialties"],
        "equipment": [e for e in h["equipment"] if e in EQUIPMENT],
        "score": round(score, 1),
        "score_breakdown": score_breakdown,
        "match_pct": min(99, round(score)),
        "readiness": readiness,
        "reason": reason,
    }


def search(conn: Connection, plan: SearchPlan, lat: float, lng: float, tier: str | None,
           limit: int = 4, max_km: float = 30.0) -> tuple[list[dict], str, str | None]:
    """Returns (ranked results, SQL actually used, relax note)."""
    sql_text = ""
    for level in (0, 1, 2):
        docs, sql_text = fetch_docs(conn, build_filter(plan, tier, level))
        scored = [score_hospital(d, plan, lat, lng, max_km) for d in docs]
        nearby = [s for s in scored if s["distance_km"] <= max_km] or scored
        if nearby:
            nearby.sort(key=lambda x: (-x["score"], x["distance_km"]))
            return nearby[:limit], sql_text, RELAX_NOTES[level]
    # Tier filter too narrow -> drop it as a last resort
    if tier and tier != "any":
        res, sql_text, _ = search(conn, plan, lat, lng, None, limit, max_km)
        return res, sql_text, "No hospital in the selected price tier fits — showing all tiers."
    return [], sql_text, None
