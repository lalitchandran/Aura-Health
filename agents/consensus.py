from typing import Dict, List, Tuple

class ConsensusEngine:
    """
    Calculates the Confidence Index (CI) and determines the final Action.
    """
    def calculate_consensus(self, clinical_score: float, forensic_score: float, trust_score: float) -> Tuple[float, str, List[str]]:
        # Weighted average for Confidence Index (CI)
        # CI represents Confidence in LEGITIMACY. High CI = Approve.
        weights = {
            "clinical": 0.35,
            "forensic": 0.45,  # Highest weight to duplicate/anomaly checks
            "trust": 0.20
        }
        
        ci_score = (
            clinical_score * weights["clinical"] +
            forensic_score * weights["forensic"] +
            trust_score * weights["trust"]
        )
        
        # Round to 2 decimal places
        ci_score = round(ci_score, 2)
        
        reasons = []
        action = "Reviewed" # Amber
        
        if ci_score > 0.85:
            action = "Fast-tracked" # Green
            reasons.append(f"High Confidence Index ({ci_score}): Claim Auto-Approved.")
        elif 0.40 <= ci_score <= 0.85:
            action = "Reviewed" # Amber
            reasons.append(f"Moderate Confidence Index ({ci_score}): Claim flagged for Manual Review.")
        else:
            action = "Rejected" # Red
            reasons.append(f"Low Confidence Index ({ci_score}): Claim Blocked/Alerted.")
            
        return ci_score, action, reasons
