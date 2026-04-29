import asyncio
from typing import Dict
from database import get_historical_claims
from agents.clinical_agent import ClinicalIntegrityAgent
from agents.forensic_agent import FinancialForensicAgent
from agents.trust_agent import NetworkTrustAgent
from agents.consensus import ConsensusEngine

class Orchestrator:
    """
    The Brain: Routes claims, queries agents in parallel, and returns the final consensus.
    """
    def __init__(self):
        # We fetch history once per Orchestrator instantiation for live claims.
        # In a fully real-time system, this might query the DB dynamically.
        self.history_df = get_historical_claims()
        self.clinical_agent = ClinicalIntegrityAgent()
        self.forensic_agent = FinancialForensicAgent(self.history_df)
        self.trust_agent = NetworkTrustAgent(self.history_df)
        self.consensus_engine = ConsensusEngine()

    async def route_claim(self, claim: Dict) -> Dict:
        # Query agents in parallel
        clinical_task = self.clinical_agent.analyze(claim)
        forensic_task = self.forensic_agent.analyze(claim)
        trust_task = self.trust_agent.analyze(claim)
        
        clinical_result, forensic_result, trust_result = await asyncio.gather(
            clinical_task, forensic_task, trust_task
        )
        
        clin_score, clin_reasons = clinical_result
        for_score, for_reasons = forensic_result
        trust_score, trust_reasons = trust_result
        
        # Pass to Consensus Engine
        ci_score, action, consensus_reasons = self.consensus_engine.calculate_consensus(
            clin_score, for_score, trust_score
        )
        
        # Package explainability
        all_reasons = clin_reasons + for_reasons + trust_reasons + consensus_reasons
        
        explainability = {
            "clinical": {"score": clin_score, "reasons": clin_reasons},
            "forensic": {"score": for_score, "reasons": for_reasons},
            "trust": {"score": trust_score, "reasons": trust_reasons},
            "consensus": {"ci_score": ci_score, "action": action, "reasons": consensus_reasons}
        }
        
        return {
            "claim": claim,
            "decision": action,
            "ci_score": ci_score,
            "reasons": all_reasons,
            "explainability": explainability
        }
