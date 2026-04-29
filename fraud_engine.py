import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

DIAGNOSIS_TO_PROCEDURES = {
    "D001": ["PROC-101", "PROC-102"],
    "D002": ["PROC-113", "PROC-121"],
    "D010": ["PROC-121", "PROC-130"],
    "D015": ["PROC-121", "PROC-130"],
    "D021": ["PROC-211", "PROC-220"],
    "D030": ["PROC-233", "PROC-241"],
    "D041": ["PROC-256", "PROC-311"],
    "D050": ["PROC-329", "PROC-341"],
    "D060": ["PROC-355"],
    "D072": ["PROC-101", "PROC-233", "PROC-355"],
}


def _normalize_procedure_codes(claim_data: Dict) -> List[str]:
    procedures = claim_data.get("procedure_codes")
    if isinstance(procedures, list):
        return [str(item).strip() for item in procedures if str(item).strip()]

    if isinstance(procedures, str) and procedures.strip():
        return [item.strip() for item in procedures.split(";") if item.strip()]

    fallback = claim_data.get("procedure_code")
    if isinstance(fallback, str) and fallback.strip():
        return [fallback.strip()]

    return []


def _normalize_date(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(value, errors="coerce")
    except Exception:
        return None


def _generate_claim_hash(claim_data: Dict) -> str:
    normalized = {k: claim_data[k] for k in sorted(claim_data) if k != "claim_hash"}
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def evaluate_claim(claim_data: Dict, historical_claims_db: pd.DataFrame) -> Dict:
    claim = dict(claim_data)
    claim["claim_hash"] = _generate_claim_hash(claim)

    decision = "Fast-tracked"
    rule_triggered: Optional[str] = None
    explanation: str = "Claim passed all real-time fraud rules."
    reasons: List[str] = []
    procedures = _normalize_procedure_codes(claim)
    patient_id = claim.get("patient_id")
    provider_id = claim.get("provider_id")
    diagnosis_code = claim.get("diagnosis_code")
    admission_date = _normalize_date(claim.get("admission_date")) or datetime.utcnow()

    if patient_id and procedures and not historical_claims_db.empty:
        recent_start = admission_date - timedelta(days=30)
        history = historical_claims_db.copy()
        history["admission_date_parsed"] = history["admission_date"].apply(_normalize_date)
        history = history[history["admission_date_parsed"].notna()]
        history = history[(history["patient_id"] == patient_id) &
                          (history["admission_date_parsed"] >= recent_start) &
                          (history["admission_date_parsed"] <= admission_date)]
        if not history.empty:
            for code in procedures:
                matches = history[history["procedure_codes"].fillna("").str.contains(code, na=False)]
                if not matches.empty:
                    decision = "Rejected"
                    rule_triggered = "Duplicate Billing"
                    explanation = (
                        f"Patient {patient_id} already filed procedure {code} within 30 days; duplicate billing rule triggered."
                    )
                    reasons.append("Duplicate billing detected within the last 30 days")
                    break

    if decision != "Rejected" and diagnosis_code and procedures:
        valid_procedures = DIAGNOSIS_TO_PROCEDURES.get(diagnosis_code, [])
        if valid_procedures:
            invalid = [code for code in procedures if code not in valid_procedures]
            if invalid:
                decision = "Reviewed"
                rule_triggered = "Diagnosis-Procedure Mismatch"
                explanation = (
                    f"Procedure code(s) {', '.join(invalid)} are not consistent with diagnosis {diagnosis_code}."
                )
                reasons.append("Procedure does not match diagnosis mapping")

    if decision == "Fast-tracked" and provider_id and not historical_claims_db.empty:
        request_time = admission_date
        recent_threshold = request_time - timedelta(hours=1)
        history = historical_claims_db.copy()
        history["admission_date_parsed"] = history["admission_date"].apply(_normalize_date)
        history = history[history["admission_date_parsed"].notna()]
        provider_recent = history[(history["provider_id"] == provider_id) &
                                  (history["admission_date_parsed"] >= recent_threshold) &
                                  (history["admission_date_parsed"] <= request_time)]
        if len(provider_recent) > 10:
            decision = "Reviewed"
            rule_triggered = "Provider Velocity"
            explanation = (
                f"Provider {provider_id} submitted {len(provider_recent)} claims in the last hour; review required."
            )
            reasons.append("Provider has high submission velocity in the last hour")

    if decision == "Fast-tracked" and not reasons:
        reasons.append("Claim passed all real-time fraud rules")
        rule_triggered = "No issues detected"
        explanation = "Claim passed the automated fraud rules and is fast-tracked for payment."

    return {
        "claim": claim,
        "decision": decision,
        "rule_triggered": rule_triggered,
        "explanation": explanation,
        "reasons": reasons,
    }
