import os
import random
from datetime import datetime, timedelta
import pandas as pd

ROOT = os.path.dirname(__file__)
SAMPLE_FILE = os.path.join(ROOT, "sample_claims.csv")

PROVIDERS = [
    {"provider_id": "P001", "provider_name": "Swasthya Health", "network": "Arogya"},
    {"provider_id": "P002", "provider_name": "Care Trust", "network": "Swasthya"},
    {"provider_id": "P003", "provider_name": "Healing Hands", "network": "Arogya"},
    {"provider_id": "P004", "provider_name": "City Diagnostics", "network": "Niramaya"},
    {"provider_id": "P005", "provider_name": "Prime Hospitals", "network": "Swasthya"},
    {"provider_id": "P006", "provider_name": "Wellness Centre", "network": "Niramaya"},
    {"provider_id": "P007", "provider_name": "CarePoint Clinics", "network": "Arogya"},
    {"provider_id": "P008", "provider_name": "Medicure Hospitals", "network": "Swasthya"},
]

PROCEDURE_CODES = [
    "PROC-101", "PROC-102", "PROC-113", "PROC-121", "PROC-130", "PROC-211", "PROC-220",
    "PROC-233", "PROC-241", "PROC-256", "PROC-311", "PROC-329", "PROC-341", "PROC-355",
]

DIAGNOSIS_CODES = [
    "D001", "D002", "D010", "D015", "D021", "D030", "D041", "D050", "D060", "D072"
]

CLAIM_TYPES = ["inpatient", "outpatient", "diagnostic"]
GENDERS = ["M", "F", "O"]

SUSPICIOUS_PROCEDURES = {"PROC-121", "PROC-233", "PROC-355"}


def _make_claim(claim_id, provider, patient_id, claim_date, procedure_codes, billed_amount, diagnosis_code, claim_type, age, gender):
    discharge_date = claim_date + timedelta(days=random.choice([0, 1, 2, 3, 5, 7]))
    return {
        "claim_id": claim_id,
        "provider_id": provider["provider_id"],
        "provider_name": provider["provider_name"],
        "network": provider["network"],
        "patient_id": f"PAT-{patient_id:04d}",
        "patient_age": age,
        "patient_gender": gender,
        "admission_date": claim_date.strftime("%Y-%m-%d"),
        "discharge_date": discharge_date.strftime("%Y-%m-%d"),
        "procedure_codes": ";".join(procedure_codes),
        "diagnosis_code": diagnosis_code,
        "claim_type": claim_type,
        "billed_amount": round(billed_amount, 2),
        "item_count": len(procedure_codes),
    }


def generate_sample_data(num_claims: int = 420, output_path: str = SAMPLE_FILE):
    random.seed(42)
    claims = []
    patient_counts = [random.randint(1, 5) for _ in range(80)]
    patient_id = 1
    base_date = datetime.today() - timedelta(days=180)

    for _ in range(num_claims):
        provider = random.choice(PROVIDERS)
        claim_date = base_date + timedelta(days=random.randint(0, 180))
        patient_age = random.randint(18, 82)
        gender = random.choice(GENDERS)
        claim_type = random.choice(CLAIM_TYPES)
        procedures = random.sample(PROCEDURE_CODES, random.randint(1, 3))
        diagnosis = random.choice(DIAGNOSIS_CODES)
        amount = 1200 + sum(450 + PROCEDURE_CODES.index(code) * 150 for code in procedures)
        amount *= random.uniform(0.9, 1.25)
        claims.append(_make_claim(f"C{len(claims)+1:05d}", provider, patient_id, claim_date, procedures, amount, diagnosis, claim_type, patient_age, gender))

        if random.random() < 0.22:
            patient_id += 1

    # Add synthetic fraud patterns
    for idx in range(1, 14):
        provider = random.choice(PROVIDERS)
        claim_date = base_date + timedelta(days=random.randint(0, 180))
        patient_age = random.randint(22, 78)
        gender = random.choice(GENDERS)
        procedures = random.sample(list(SUSPICIOUS_PROCEDURES), 1)
        diagnosis = random.choice(DIAGNOSIS_CODES)
        amount = 7000 + random.uniform(0.9, 1.4) * 2200
        claims.append(_make_claim(f"F{idx:05d}", provider, patient_id, claim_date, procedures, amount, diagnosis, "diagnostic", patient_age, gender))
        patient_id += 1

    # Add duplicate billing and ghost procedure cases
    for idx in range(1, 12):
        original = random.choice(claims)
        if idx % 3 == 0:
            ghost = original.copy()
            ghost["claim_id"] = f"G{idx:05d}"
            ghost["procedure_codes"] = ""
            ghost["billed_amount"] = round(original["billed_amount"] * 1.8, 2)
            claims.append(ghost)
        else:
            dup = original.copy()
            dup["claim_id"] = f"D{idx:05d}"
            dup["admission_date"] = (datetime.strptime(original["admission_date"], "%Y-%m-%d") + timedelta(days=random.randint(1, 4))).strftime("%Y-%m-%d")
            dup["discharge_date"] = (datetime.strptime(dup["admission_date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            claims.append(dup)

    df = pd.DataFrame(claims)
    df.to_csv(output_path, index=False)
    return df


def load_claim_history(path: str = SAMPLE_FILE) -> pd.DataFrame:
    if not os.path.exists(path):
        generate_sample_data(output_path=path)
    df = pd.read_csv(path)
    return df

if __name__ == "__main__":
    print("Generating sample claims dataset...")
    df = generate_sample_data()
    print(f"Sample data saved to {SAMPLE_FILE} with {len(df)} rows.")
