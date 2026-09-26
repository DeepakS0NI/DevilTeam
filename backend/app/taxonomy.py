"""
Fixed vocabulary shared by the database, Gemini prompt and the frontend.
Gemini is only allowed to emit tags from these lists, so its output always maps to real DB fields.
"""

SPECIALTIES = {
    "cardiology": "Cardiology",
    "neurology": "Neurology / Stroke",
    "neurosurgery": "Neurosurgery",
    "orthopedics": "Orthopaedics",
    "trauma": "Trauma & Emergency Surgery",
    "general_surgery": "General Surgery",
    "general_medicine": "General Medicine",
    "pulmonology": "Pulmonology",
    "obstetrics": "Obstetrics / Maternity",
    "pediatrics": "Paediatrics",
    "nephrology": "Nephrology",
    "gastroenterology": "Gastroenterology",
    "oncology": "Oncology",
    "burns": "Burns & Plastic Surgery",
}

EQUIPMENT = {
    "cath_lab": "Cath lab",
    "ct_scan": "CT scan",
    "mri": "MRI",
    "ventilator": "Ventilator",
    "dialysis": "Dialysis",
    "blood_bank": "Blood bank",
    "nicu": "NICU",
    "x_ray": "X-ray",
    "ultrasound": "Ultrasound",
}

TIERS = {"low": "Low cost · govt", "medium": "Medium · private", "high": "High · premium"}

# Area dropdown in the frontend -> coordinates (approx.)
AREAS = {
    "hazratganj": (26.8505, 80.9460),
    "gomti nagar": (26.8520, 81.0070),
    "aliganj": (26.8930, 80.9420),
    "alambagh": (26.8120, 80.9020),
    "indira nagar": (26.8780, 80.9980),
}
DEFAULT_AREA = "hazratganj"

# Keyword fallback, used when Gemini is not configured or fails. Hindi/Hinglish words included.
KEYWORD_MAP = {
    "chest pain": ["cardiology"], "heart": ["cardiology"], "cardiac": ["cardiology"], "palpitation": ["cardiology"],
    "seene": ["cardiology"], "dil": ["cardiology"], "angina": ["cardiology"],
    "stroke": ["neurology"], "paraly": ["neurology"], "seizure": ["neurology"], "fits": ["neurology"],
    "unconscious": ["neurology"], "behosh": ["neurology"], "slurred": ["neurology"],
    "head injury": ["neurosurgery", "trauma"], "sir pe chot": ["neurosurgery", "trauma"],
    "fracture": ["orthopedics", "trauma"], "bone": ["orthopedics", "trauma"], "bons": ["orthopedics", "trauma"],
    "haddi": ["orthopedics", "trauma"], "accident": ["trauma", "orthopedics"], "injur": ["trauma"],
    "bleed": ["trauma", "general_surgery"], "khoon": ["trauma"], "burn": ["burns"], "jal ": ["burns"],
    "breath": ["pulmonology"], "saans": ["pulmonology"], "asthma": ["pulmonology"], "oxygen": ["pulmonology"],
    "pregnan": ["obstetrics"], "labour": ["obstetrics"], "labor": ["obstetrics"], "delivery": ["obstetrics"],
    "child": ["pediatrics"], "baby": ["pediatrics"], "bacch": ["pediatrics"], "infant": ["pediatrics"],
    "kidney": ["nephrology"], "dialysis": ["nephrology"], "stomach": ["gastroenterology"], "pet ": ["gastroenterology"],
    "vomit": ["gastroenterology"], "cancer": ["oncology"], "fever": ["general_medicine"], "bukhar": ["general_medicine"],
}
