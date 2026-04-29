from typing import Dict, List, Tuple
from fraud_engine import DIAGNOSIS_TO_PROCEDURES, _normalize_procedure_codes

class ClinicalIntegrityAgent:
    """
    Checks Diagnosis vs. Treatment (Medical RAG placeholder).
    Returns a score between 0.0 (High Risk/Mismatch) and 1.0 (Valid).
    """
    async def analyze(self, claim: Dict) -> Tuple[float, List[str]]:
        reasons = []
        procedures = _normalize_procedure_codes(claim)
        diagnosis_code = claim.get("diagnosis_code")
        
        if not diagnosis_code or not procedures:
            return 0.5, ["Missing diagnosis or procedure codes for clinical evaluation."]

        valid_procedures = DIAGNOSIS_TO_PROCEDURES.get(diagnosis_code, [])
        if not valid_procedures:
            # Diagnosis not in our strict mapping; assume neutral/unknown risk
            return 0.7, [f"No strict mapping available for diagnosis {diagnosis_code}."]
            
        invalid = [code for code in procedures if code not in valid_procedures]
        
        if invalid:
            explanation = f"Procedure code(s) {', '.join(invalid)} are not consistent with diagnosis {diagnosis_code}."
            reasons.append(explanation)
            return 0.2, reasons # Low score means high risk
            
        reasons.append("Clinical evaluation passed: procedures match diagnosis.")
        return 1.0, reasons # 1.0 means perfectly valid

