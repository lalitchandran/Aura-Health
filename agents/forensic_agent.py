import pandas as pd
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
from model import FraudDetector, _make_feature_frame
from fraud_engine import _normalize_procedure_codes, _normalize_date

class FinancialForensicAgent:
    """
    Scans for Upcoding / Duplicate Bills / Anomaly Detection.
    Returns a score between 0.0 (High Risk/Anomaly) and 1.0 (Valid).
    """
    def __init__(self, history_df: pd.DataFrame):
        self.detector = FraudDetector()
        if not history_df.empty:
            self.detector.fit(history_df)
        self.history = history_df

    async def analyze(self, claim: Dict) -> Tuple[float, List[str]]:
        reasons = []
        score = 1.0 # Start with perfect score
        
        # 1. 30-day Duplicate Billing Check
        patient_id = claim.get("patient_id")
        procedures = _normalize_procedure_codes(claim)
        admission_date = _normalize_date(claim.get("admission_date")) or datetime.utcnow()
        
        if patient_id and procedures and not self.history.empty:
            recent_start = admission_date - timedelta(days=30)
            hist_copy = self.history.copy()
            hist_copy["admission_date_parsed"] = hist_copy["admission_date"].apply(_normalize_date)
            hist_copy = hist_copy[hist_copy["admission_date_parsed"].notna()]
            
            recent_history = hist_copy[
                (hist_copy["patient_id"] == patient_id) &
                (hist_copy["admission_date_parsed"] >= recent_start) &
                (hist_copy["admission_date_parsed"] <= admission_date)
            ]
            
            if not recent_history.empty:
                for code in procedures:
                    matches = recent_history[recent_history["procedure_codes"].fillna("").str.contains(code, na=False)]
                    if not matches.empty:
                        reasons.append(f"Duplicate billing: Patient already filed procedure {code} within 30 days.")
                        score = min(score, 0.1) # Extreme penalty for duplicate

        # 2. Statistical Anomaly (Isolation Forest)
        if self.detector.model is not None:
            anomaly = self.detector._anomaly_score(claim)
            if anomaly > 0.35:
                reasons.append("Statistical anomaly detected in financial/claim features.")
                score = min(score, max(0.2, 1.0 - anomaly))
                
        if score > 0.8:
            reasons.append("Forensic evaluation passed: No duplicate billing or anomalies detected.")
            
        return score, reasons

