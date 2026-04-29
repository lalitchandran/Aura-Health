import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

SUSPICIOUS_DIAGNOSIS = {"D050", "D060", "D072"}
HIGH_RISK_PROCEDURES = {"PROC-121", "PROC-233", "PROC-355"}
TRUSTED_NETWORKS = {"Arogya", "Swasthya"}


def _parse_procedure_codes(value: str) -> List[str]:
    if pd.isna(value) or not isinstance(value, str) or value.strip() == "":
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _make_feature_frame(df: pd.DataFrame, stats: Dict[str, Dict[str, float]]):
    procedures = df["procedure_codes"].apply(_parse_procedure_codes)
    procedure_count = procedures.apply(len).astype(float)
    admission_date = pd.to_datetime(df["admission_date"], errors="coerce")
    days_since_admission = (pd.Timestamp.today() - admission_date).dt.days.fillna(0).clip(lower=0)
    provider_stats = df["provider_id"].map(lambda provider_id: stats[provider_id]["avg_amount"] if provider_id in stats else df["billed_amount"].mean())
    patient_claim_count = df["patient_id"].map(lambda patient_id: stats.get(patient_id, {}).get("claim_count", 0)).astype(float)
    network_codes = df["network"].map({"Arogya": 0, "Swasthya": 1, "Niramaya": 2}).fillna(0)
    claim_type_codes = df["claim_type"].map({"inpatient": 0, "outpatient": 1, "diagnostic": 2}).fillna(1)

    return pd.DataFrame({
        "billed_amount": df["billed_amount"].astype(float).fillna(0),
        "procedure_count": procedure_count,
        "amount_per_procedure": df["billed_amount"].astype(float).divide(1 + procedure_count),
        "days_since_admission": days_since_admission,
        "provider_avg_amount": provider_stats,
        "patient_claim_count": patient_claim_count,
        "network_code": network_codes,
        "claim_type_code": claim_type_codes,
    }).fillna(0)


class AuditTrail:
    def __init__(self):
        self.chain = []

    def record(self, claim: Dict, decision: str, score: float, reasons: List[str]) -> Dict:
        payload = {
            "claim_id": claim.get("claim_id"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision": decision,
            "risk_score": round(score, 4),
            "reasons": reasons,
            "claim_snapshot": claim,
        }
        payload_str = json.dumps(payload, sort_keys=True)
        entry_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        prev_hash = self.chain[-1]["hash"] if self.chain else None
        entry = {"hash": entry_hash, "previous_hash": prev_hash, "payload": payload}
        self.chain.append(entry)
        return entry

    def all_entries(self) -> List[Dict]:
        return self.chain.copy()


class FraudDetector:
    def __init__(self):
        self.history = pd.DataFrame()
        self.model: Optional[IsolationForest] = None
        self.provider_profile = {}
        self.patient_profile = {}
        self.audit_trail = AuditTrail()
        self.live_claims = []

    def fit(self, history: pd.DataFrame):
        self.history = history.copy()
        self.history["procedure_codes"] = self.history["procedure_codes"].fillna("")
        self.history["billed_amount"] = self.history["billed_amount"].astype(float).fillna(0)
        provider_groups = self.history.groupby("provider_id")
        self.provider_profile = {
            provider_id: {
                "claim_count": len(group),
                "avg_amount": float(group["billed_amount"].mean()),
                "max_amount": float(group["billed_amount"].max()),
                "unique_patients": group["patient_id"].nunique(),
                "network": group["network"].mode().iloc[0] if not group["network"].mode().empty else "unknown",
            }
            for provider_id, group in provider_groups
        }
        patient_groups = self.history.groupby("patient_id")
        self.patient_profile = {
            patient_id: {"claim_count": len(group), "avg_amount": float(group["billed_amount"].mean())}
            for patient_id, group in patient_groups
        }
        features = _make_feature_frame(self.history, self.provider_profile)
        self.model = IsolationForest(n_estimators=200, contamination=0.03, random_state=42)
        self.model.fit(features)

    def _score_by_rules(self, claim: Dict) -> List[str]:
        reasons = []
        procedures = _parse_procedure_codes(claim.get("procedure_codes", ""))
        amount = float(claim.get("billed_amount", 0))
        provider_id = claim.get("provider_id")
        diagnosis = claim.get("diagnosis_code")
        patient_id = claim.get("patient_id")

        if not procedures:
            reasons.append("no procedure codes found; possible ghost procedure")

        if diagnosis in SUSPICIOUS_DIAGNOSIS:
            reasons.append("suspicious diagnosis code")

        if any(code in HIGH_RISK_PROCEDURES for code in procedures):
            reasons.append("high-risk or inflated procedure code")

        if provider_id in self.provider_profile:
            provider_avg = self.provider_profile[provider_id]["avg_amount"]
            if amount > provider_avg * 2.0:
                reasons.append("billed amount is more than twice provider average")

        if patient_id in self.patient_profile and amount > self.patient_profile[patient_id]["avg_amount"] * 2.0:
            reasons.append("patient amount is unusually high compared to history")

        return reasons

    def _build_single_feature(self, claim: Dict):
        df = pd.DataFrame([claim])
        return _make_feature_frame(df, self.provider_profile)

    def detect_duplicate(self, claim: Dict) -> bool:
        duplicate_criteria = [
            (self.history["patient_id"] == claim.get("patient_id")) &
            (self.history["provider_id"] == claim.get("provider_id")) &
            (self.history["procedure_codes"] == claim.get("procedure_codes")) &
            (self.history["billed_amount"] == float(claim.get("billed_amount", 0)))
        ]
        if self.live_claims:
            live_df = pd.DataFrame(self.live_claims)
            duplicate_criteria.append(
                (live_df["patient_id"] == claim.get("patient_id")) &
                (live_df["provider_id"] == claim.get("provider_id")) &
                (live_df["procedure_codes"] == claim.get("procedure_codes")) &
                (live_df["billed_amount"] == float(claim.get("billed_amount", 0)))
            )
        return any(criteria.any() for criteria in duplicate_criteria)

    def _anomaly_score(self, claim: Dict) -> float:
        if self.model is None:
            return 0.0
        feature = self._build_single_feature(claim)
        score = float(self.model.decision_function(feature).reshape(-1)[0])
        normalized = max(0.0, min(1.0, (-score + 0.2) / 0.6))
        return normalized

    def evaluate_claim(self, claim: Dict) -> Dict:
        reasons = self._score_by_rules(claim)
        duplicate = self.detect_duplicate(claim)
        if duplicate:
            reasons.append("duplicate billing pattern detected")

        anomaly = self._anomaly_score(claim)
        if anomaly > 0.35:
            reasons.append("statistical anomaly detected in claim features")

        risk_score = 0.0
        if duplicate:
            risk_score += 0.38
        if any("suspicious" in reason for reason in reasons):
            risk_score += 0.16
        risk_score += anomaly * 0.42
        risk_score = min(1.0, risk_score)

        verdict = "review"
        if risk_score < 0.25:
            verdict = "fast-tracked"
        elif risk_score < 0.55:
            verdict = "approved"
        elif risk_score < 0.78:
            verdict = "review"
        else:
            verdict = "rejected"

        if claim.get("provider_id") in self.provider_profile:
            trust_factor = self.provider_profile[claim["provider_id"]]["avg_amount"] < 7000
            if trust_factor and risk_score < 0.20:
                verdict = "fast-tracked"

        audit_entry = self.audit_trail.record(claim, verdict, risk_score, reasons)
        self.live_claims.append(claim.copy())
        return {
            "risk_score": round(risk_score, 4),
            "verdict": verdict,
            "reasons": reasons,
            "audit_entry": audit_entry,
        }

    def provider_summary(self):
        summary = []
        for provider_id, metrics in self.provider_profile.items():
            summary.append({
                "provider_id": provider_id,
                "avg_amount": metrics["avg_amount"],
                "claim_count": metrics["claim_count"],
                "unique_patients": metrics["unique_patients"],
                "network": metrics.get("network", "unknown"),
            })
        return sorted(summary, key=lambda item: item["avg_amount"], reverse=True)

    def audit_chain(self):
        return self.audit_trail.all_entries()
