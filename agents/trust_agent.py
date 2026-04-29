import pandas as pd
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
from fraud_engine import _normalize_date

class NetworkTrustAgent:
    """
    Checks Provider/Hospital Reputation and City/Network Averages.
    Returns a score between 0.0 (High Risk/Untrusted) and 1.0 (Trusted).
    """
    def __init__(self, history_df: pd.DataFrame):
        self.history = history_df
        self.provider_stats = {}
        if not history_df.empty:
            history_df["billed_amount"] = history_df["billed_amount"].astype(float).fillna(0)
            groups = history_df.groupby("provider_id")
            self.provider_stats = {
                provider_id: {
                    "avg_amount": float(group["billed_amount"].mean()),
                    "claim_count": len(group)
                }
                for provider_id, group in groups
            }

    async def analyze(self, claim: Dict) -> Tuple[float, List[str]]:
        reasons = []
        score = 1.0
        
        provider_id = claim.get("provider_id")
        amount = float(claim.get("billed_amount", 0))
        admission_date = _normalize_date(claim.get("admission_date")) or datetime.utcnow()
        
        # 1. Provider Reputation / Average Cost
        if provider_id in self.provider_stats:
            provider_avg = self.provider_stats[provider_id]["avg_amount"]
            if amount > provider_avg * 2.0:
                reasons.append(f"Trust flag: Billed amount (₹{amount}) is more than twice the provider's average (₹{provider_avg:.2f}).")
                score -= 0.3
        
        # 2. Provider Velocity (Too many claims in last hour)
        if provider_id and not self.history.empty:
            recent_threshold = admission_date - timedelta(hours=1)
            hist_copy = self.history.copy()
            hist_copy["admission_date_parsed"] = hist_copy["admission_date"].apply(_normalize_date)
            hist_copy = hist_copy[hist_copy["admission_date_parsed"].notna()]
            
            provider_recent = hist_copy[
                (hist_copy["provider_id"] == provider_id) &
                (hist_copy["admission_date_parsed"] >= recent_threshold) &
                (hist_copy["admission_date_parsed"] <= admission_date)
            ]
            
            if len(provider_recent) > 10:
                reasons.append(f"Velocity flag: Provider submitted {len(provider_recent)} claims in the last hour.")
                score -= 0.4
                
        score = max(0.0, score)
        if score > 0.8:
            reasons.append("Trust evaluation passed: Provider reputation and velocity are within normal limits.")
            
        return score, reasons

