"""
The AI part of the RAG pipeline (Gemini).

  1. understand_query()   text  -> structured filter (JSON, only DB-known tags)
                          Retrieval-grounded: the allowed tags come live from the SQL database (DISTINCT values),
                          so Gemini can never invent a facility the database doesn't have.
  2. (search.py)          filter -> SQL query -> ranked hospitals   <- the "Retrieval"
  3. write_recommendation() top hospitals (real DB docs) -> short grounded explanation  <- the "Generation"

If GEMINI_API_KEY is missing or Gemini errors, a keyword fallback keeps the app working.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from . import config
from .taxonomy import EQUIPMENT, KEYWORD_MAP, SPECIALTIES

log = logging.getLogger("careshift.gemini")

_client = None


def _get_client():
    """Lazy Gemini client. Returns None when no key is configured."""
    global _client
    if _client is None and config.GEMINI_API_KEY:
        from google import genai
        from google.genai import types

        # 🔑 Gemini API key yahan use hoti hai (config.py -> .env -> GEMINI_API_KEY)
        _client = genai.Client(api_key=config.GEMINI_API_KEY,
                               http_options=types.HttpOptions(timeout=20_000))
    return _client


# ---------------------------------------------------------------- 1. Query understanding

class GeminiPlan(BaseModel):
    """Exact JSON shape Gemini must return (structured output)."""
    condition_summary: str = Field(description="One short line in English: what is likely happening")
    specialties: list[str] = Field(description="Needed specialties, most important first. Only allowed tags.")
    equipment: list[str] = Field(description="Equipment that is clearly essential. Only allowed tags. Usually 0-2.")
    needs_icu: bool
    needs_ventilator: bool
    needs_ot: bool = Field(description="True if emergency surgery is likely")
    needs_ambulance: bool = Field(description="True if patient can't travel or user asks for ambulance")
    severity: Literal["critical", "urgent", "routine"]
    red_flags: list[str] = Field(description="Short danger signs found in the text")
    confidence: float = Field(description="0 to 1, how sure you are about the specialties")


class SearchPlan(GeminiPlan):
    source: Literal["gemini", "keywords"] = "gemini"


SYSTEM_PROMPT = """You are the triage-routing brain of CareShift AI, an emergency hospital finder in Lucknow, India.
Convert the user's free-text emergency description (English, Hindi or Hinglish, often misspelled) into a
database filter. You do NOT diagnose or give treatment advice; you only decide which hospital facilities are needed.

Rules:
- Use ONLY tags from the allowed lists below. Never invent tags.
- specialties: 1-3 tags, most important first. Examples: chest pain -> cardiology; broken/damaged bones or
  "haddi toot gayi" -> orthopedics + trauma; road accident -> trauma + orthopedics; stroke/slurred speech ->
  neurology; head injury -> neurosurgery + trauma; breathing trouble -> pulmonology; pregnancy/labour ->
  obstetrics; child/baby -> pediatrics (+ the organ system); burns -> burns.
- equipment: only when clearly essential (heart attack -> cath_lab; stroke/head injury -> ct_scan;
  heavy bleeding -> blood_bank; newborn -> nicu; kidney failure -> dialysis). Otherwise empty.
- needs_icu for unconsciousness, severe breathing trouble, major trauma, heart attack, stroke.
- needs_ventilator only if not breathing / severe respiratory failure.
- needs_ot if emergency surgery is likely (major fracture, heavy bleeding, head injury, obstetric emergency).
- If the text is vague, choose general_medicine and lower confidence.

Allowed specialties: {specialties}
Allowed equipment: {equipment}"""


def understand_query(text: str, urgency: str | None, allowed_specs: list[str], allowed_equip: list[str]) -> SearchPlan:
    client = _get_client()
    if client is not None:
        try:
            from google.genai import types

            prompt = f"Emergency description: {text}\nUser-selected urgency: {urgency or 'not given'}"
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT.format(specialties=", ".join(allowed_specs),
                                                            equipment=", ".join(allowed_equip)),
                    response_mime_type="application/json",
                    response_schema=GeminiPlan,
                    temperature=0.1,
                ),
            )
            raw = resp.parsed or GeminiPlan.model_validate_json(resp.text)
            plan = SearchPlan(**raw.model_dump(), source="gemini")
            # Guard-rail: drop anything outside the DB vocabulary
            plan.specialties = [s for s in plan.specialties if s in allowed_specs][:3]
            plan.equipment = [e for e in plan.equipment if e in allowed_equip][:3]
            if plan.specialties:
                return plan
            log.warning("Gemini returned no valid specialties, using keyword fallback")
        except Exception as e:  # network, quota, safety block, bad JSON...
            log.warning("Gemini parse failed (%s), using keyword fallback", e)
    return keyword_plan(text, urgency)


def keyword_plan(text: str, urgency: str | None) -> SearchPlan:
    t = f" {text.lower()} "
    specs: list[str] = []
    for key, tags in KEYWORD_MAP.items():
        if key in t:
            specs += [s for s in tags if s not in specs]
    severe = any(w in t for w in ("unconscious", "behosh", "not breathing", "heavy bleed", "severe", "bahut"))
    severity = "critical" if urgency == "critical" or severe else ("urgent" if urgency == "urgent" else "routine")
    equip = []
    if "cardiology" in specs and severity == "critical":
        equip.append("cath_lab")
    return SearchPlan(
        condition_summary=f"Needs {', '.join(SPECIALTIES[s] for s in specs[:2])}" if specs else "General emergency",
        specialties=specs[:3] or ["general_medicine"],
        equipment=equip,
        needs_icu=severity == "critical",
        needs_ventilator="not breathing" in t,
        needs_ot=any(s in specs for s in ("orthopedics", "trauma", "neurosurgery")) and severity != "routine",
        needs_ambulance="ambulance" in t,
        severity=severity,
        red_flags=[],
        confidence=0.6 if specs else 0.3,
        source="keywords",
    )


# ---------------------------------------------------------------- 3. Grounded recommendation

EXPLAIN_PROMPT = """You are CareShift Copilot. Using ONLY the hospital records below (retrieved from our live
database), write 2-3 short sentences for a stressed family member:
- say which hospital is the best match and why (specialty on duty, ICU/OT free, distance);
- mention one backup option;
- end with: confirm with the hospital before travelling, and call 108 if life-threatening.
Reply in the same language/script the user wrote in (English, Hindi or Hinglish). Do not diagnose.
Do not mention any facility or number that is not in the records.

User text: {text}
Understood need: {summary}
Records (best first): {records}"""


def write_recommendation(text: str, plan: SearchPlan, results: list[dict]) -> tuple[str, str]:
    if not results:
        return ("No hospital in our network matches all requirements right now. Please call 108 immediately "
                "for emergency help.", "no_results")
    client = _get_client()
    if client is not None and plan.source == "gemini":
        try:
            records = [{k: r[k] for k in ("name", "area", "distance_km", "eta_min", "matched_specialties",
                                           "specialist", "icu", "ot", "tier_label")} for r in results[:3]]
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=EXPLAIN_PROMPT.format(text=text, summary=plan.condition_summary,
                                               records=json.dumps(records, ensure_ascii=False)),
                config={"temperature": 0.3, "max_output_tokens": 220},
            )
            if resp.text:
                return resp.text.strip(), "gemini"
        except Exception as e:
            log.warning("Gemini explain failed (%s), using template", e)
    return template_recommendation(plan, results), "template"


def template_recommendation(plan: SearchPlan, results: list[dict]) -> str:
    top = results[0]
    parts = [f"{top['name']} is the strongest match — {top['distance_km']} km away"]
    if top["matched_specialties"]:
        parts.append(f"with {', '.join(SPECIALTIES[s] for s in top['matched_specialties'])} available")
    parts.append(f"and {top['icu']} ICU bed(s) / {top['ot']} OT free.")
    msg = " ".join(parts)
    if len(results) > 1:
        msg += f" Backup: {results[1]['name']} ({results[1]['distance_km']} km)."
    return msg + " Please confirm with the hospital before travelling; call 108 if life-threatening."
