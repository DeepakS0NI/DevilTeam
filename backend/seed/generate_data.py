"""
Generates seed/hospitals.json — SYNTHETIC demo data for Lucknow (capacity numbers are made up).
Run:  python seed/generate_data.py
"""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

random.seed(7)

# name, area, lat, lng, tier, specialties, equipment
HOSPITALS = [
    ("SGPGI Emergency & Trauma Centre", "Raebareli Rd", 26.7445, 80.9383, "low",
     ["cardiology", "neurology", "neurosurgery", "trauma", "pulmonology", "nephrology", "gastroenterology", "general_surgery"],
     ["cath_lab", "ct_scan", "mri", "ventilator", "dialysis", "blood_bank", "x_ray", "ultrasound"]),
    ("KGMU Trauma Centre", "Chowk", 26.8690, 80.9170, "low",
     ["trauma", "orthopedics", "neurosurgery", "neurology", "general_surgery", "burns", "general_medicine"],
     ["ct_scan", "mri", "ventilator", "blood_bank", "x_ray", "ultrasound"]),
    ("RMLIMS Emergency", "Vibhuti Khand", 26.8627, 81.0000, "low",
     ["general_medicine", "obstetrics", "trauma", "pediatrics", "general_surgery"],
     ["ct_scan", "ventilator", "blood_bank", "nicu", "x_ray", "ultrasound"]),
    ("Sahara Hospital", "Gomti Nagar", 26.8580, 81.0005, "medium",
     ["cardiology", "general_medicine", "obstetrics", "orthopedics", "pediatrics"],
     ["cath_lab", "ct_scan", "ventilator", "blood_bank", "nicu", "x_ray", "ultrasound"]),
    ("Medanta Hospital", "Sushant Golf City", 26.7640, 80.9860, "high",
     ["cardiology", "neurology", "neurosurgery", "pulmonology", "oncology", "nephrology", "orthopedics"],
     ["cath_lab", "ct_scan", "mri", "ventilator", "dialysis", "blood_bank", "x_ray", "ultrasound"]),
    ("Apollomedics Super Speciality", "Kanpur Rd", 26.7960, 80.8870, "high",
     ["cardiology", "trauma", "pulmonology", "general_medicine", "gastroenterology", "orthopedics"],
     ["cath_lab", "ct_scan", "mri", "ventilator", "blood_bank", "x_ray", "ultrasound"]),
    # Fictional hospitals below (to make filtering interesting)
    ("Gomti Heart & Vascular", "Gomti Nagar Ext.", 26.8390, 81.0260, "medium",
     ["cardiology", "general_medicine"], ["cath_lab", "ct_scan", "ventilator", "x_ray", "ultrasound"]),
    ("Awadh Ortho & Trauma", "Alambagh", 26.8150, 80.9050, "medium",
     ["orthopedics", "trauma", "general_surgery"], ["ct_scan", "mri", "blood_bank", "x_ray"]),
    ("NovaNeuro Sciences", "Aliganj", 26.8960, 80.9450, "high",
     ["neurology", "neurosurgery"], ["ct_scan", "mri", "ventilator", "x_ray"]),
    ("Shakti Women & Child", "Indira Nagar", 26.8800, 80.9950, "medium",
     ["obstetrics", "pediatrics"], ["nicu", "ultrasound", "blood_bank"]),
    ("Sunrise Children's Hospital", "Mahanagar", 26.8770, 80.9580, "medium",
     ["pediatrics", "general_medicine"], ["nicu", "ventilator", "x_ray", "ultrasound"]),
    ("Unity Burns Centre", "Charbagh", 26.8320, 80.9220, "low",
     ["burns", "general_surgery"], ["ventilator", "blood_bank", "x_ray"]),
    ("Kaveri Kidney Care", "Hazratganj", 26.8520, 80.9480, "medium",
     ["nephrology"], ["dialysis", "ultrasound", "x_ray"]),
    ("Lotus Emergency & Trauma", "Hazratganj", 26.8470, 80.9400, "medium",
     ["trauma", "orthopedics", "general_surgery", "general_medicine"],
     ["ct_scan", "ventilator", "blood_bank", "x_ray", "ultrasound"]),
    ("Civil District Hospital", "Hazratganj", 26.8560, 80.9420, "low",
     ["general_medicine", "general_surgery", "obstetrics", "pediatrics"], ["x_ray", "ultrasound", "blood_bank"]),
    ("Pulse Chest & Lung Institute", "Aliganj", 26.8890, 80.9360, "medium",
     ["pulmonology", "general_medicine"], ["ct_scan", "ventilator", "x_ray"]),
    ("Harmony Cancer Institute", "Faizabad Rd", 26.8750, 81.0200, "high",
     ["oncology", "general_surgery"], ["ct_scan", "mri", "blood_bank", "ultrasound"]),
    ("CityCare Multispeciality", "Indira Nagar", 26.8830, 81.0050, "medium",
     ["cardiology", "orthopedics", "trauma", "neurology", "general_medicine", "gastroenterology"],
     ["cath_lab", "ct_scan", "mri", "ventilator", "blood_bank", "x_ray", "ultrasound"]),
    ("Metro Gastro Clinic", "Alambagh", 26.8090, 80.8980, "medium",
     ["gastroenterology", "general_medicine"], ["ultrasound", "x_ray"]),
    ("Orchid Day Care", "Gomti Nagar", 26.8600, 81.0100, "medium",
     ["general_surgery"], ["x_ray", "ultrasound"]),
]

COST = {"low": "₹ Subsidised govt rates", "medium": "₹₹ Private, mid-range", "high": "₹₹₹ Premium super-speciality"}
DOCTORS = ["Mehra", "Rawat", "Verma", "Singh", "Kapoor", "Srivastava", "Khan", "Tiwari", "Agarwal", "Mishra",
           "Pandey", "Saxena", "Dixit", "Yadav", "Rizvi", "Shukla", "Bajpai", "Awasthi"]


def build():
    docs = []
    for i, (name, area, lat, lng, tier, specs, equip) in enumerate(HOSPITALS, start=1):
        big = len(specs) >= 5
        icu_total = random.randint(12, 40) if big else random.randint(0, 10)
        ot_total = random.randint(3, 10) if big else random.randint(0, 3)
        on_duty = [s for s in specs if random.random() > 0.25]  # ~75% specialties staffed right now
        docs.append({
            "_id": f"H{i:03d}",
            "name": name,
            "area": area,
            "city": "Lucknow",
            "phone": f"0522-{random.randint(2000000, 4999999)}",
            "location": {"type": "Point", "coordinates": [lng, lat]},  # GeoJSON: [lng, lat]
            "tier": tier,
            "cost": COST[tier],
            "rating": round(random.uniform(3.8, 4.8), 1),
            "emergency_24x7": name != "Orchid Day Care",
            "specialties": sorted(specs),
            "specialists_on_duty": [{"specialty": s, "doctor": f"Dr. {random.choice(DOCTORS)}"} for s in sorted(on_duty)],
            "equipment": sorted(equip),
            "capacity": {
                "icu_total": icu_total,
                "icu_available": random.randint(0, icu_total) if icu_total else 0,
                "ventilators_available": random.randint(0, 8) if "ventilator" in equip else 0,
                "ot_total": ot_total,
                "ot_available": random.randint(0, ot_total) if ot_total else 0,
                "general_beds_available": random.randint(0, 60) if big else random.randint(0, 15),
            },
            "ambulance": {"available": random.randint(0, 4) if big else random.randint(0, 1),
                          "als": big and random.random() > 0.3},
            "accepts_ayushman_bharat": tier == "low" or random.random() > 0.5,
            "synthetic": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return docs


if __name__ == "__main__":
    out = Path(__file__).with_name("hospitals.json")
    data = build()
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(data)} hospitals -> {out}")
