import os
import asyncio
import pandas as pd
from flask import Flask, jsonify, request, render_template

from database import get_historical_claims, insert_claim, get_connection
from agents.orchestrator import Orchestrator
from data_generator import PROVIDERS, PROCEDURE_CODES, DIAGNOSIS_CODES
import random
import uuid

app = Flask(__name__)
API_KEY = "SENTINEL-SECURE-KEY-2026"

def _mock_patient_name(patient_id: str) -> str:
    if not patient_id: return "Unknown Patient"
    return f"Patient {patient_id[-4:]}"

def _mock_provider_name(provider_id: str) -> str:
    if not provider_id: return "Unknown Provider"
    return f"Provider {provider_id[-4:]}"

def _summary_records(records: pd.DataFrame, columns: list) -> list:
    return records[columns].fillna("N/A").to_dict(orient="records")

@app.route("/submit-claim", methods=["POST"])
async def submit_claim():
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Unauthorized. Invalid or missing API Key."}), 401

    claim = request.get_json(silent=True)
    if not claim or not isinstance(claim, dict):
        return jsonify({"error": "Request body must be valid JSON claim data."}), 400
        
    patient_id = claim.get("patient_id")
    if not patient_id:
        return jsonify({"error": "Missing required field: patient_id"}), 400
        
    # Auto-generate missing fields for the simulator
    if not claim.get("claim_id"):
        claim["claim_id"] = f"SIM-{str(uuid.uuid4())[:8].upper()}"
        
    if not claim.get("provider_id"):
        provider = random.choice(PROVIDERS)
        claim["provider_id"] = provider["provider_id"]
        claim["provider_name"] = provider["provider_name"]
        claim["network"] = provider["network"]
        
    if not claim.get("diagnosis_code"):
        claim["diagnosis_code"] = random.choice(DIAGNOSIS_CODES)
        
    if not claim.get("procedure_code"):
        procedures = random.sample(PROCEDURE_CODES, random.randint(1, 2))
        claim["procedure_code"] = procedures[0]
        claim["procedure_codes"] = ";".join(procedures)
        
    if not claim.get("billed_amount"):
        claim["billed_amount"] = round(random.uniform(1500, 12000), 2)
    else:
        try:
            claim["billed_amount"] = float(claim["billed_amount"])
        except ValueError:
            return jsonify({"error": "Billed amount must be numeric."}), 400

    # Instantiate Orchestrator (it fetches fresh DB history internally)
    orchestrator = Orchestrator()
    result = await orchestrator.route_claim(claim)
    
    # Save the evaluated claim
    evaluated_claim = result["claim"].copy()
    evaluated_claim["decision"] = result["decision"]
    evaluated_claim["decision_reasons"] = ";".join(result["reasons"])
    # Not using rule_triggered or explanation in the same way, but we can store the CI score
    evaluated_claim["rule_triggered"] = f"CI Score: {result['ci_score']}"
    evaluated_claim["explanation"] = f"Agentic Workflow: {result['decision']}"

    # Insert to SQLite database
    insert_claim(evaluated_claim)

    return jsonify({
        "claim_id": evaluated_claim.get("claim_id"),
        "decision": result["decision"],
        "ci_score": result["ci_score"],
        "reasons": result["reasons"],
        "explainability": result["explainability"],
        "claim_details": evaluated_claim
    })

@app.route("/api/audit/<claim_id>", methods=["GET"])
def audit_claim(claim_id):
    claim_history = get_historical_claims()
    claim_rows = claim_history[claim_history["claim_id"] == claim_id]
    if claim_rows.empty:
        return jsonify({"error": f"Claim {claim_id} not found."}), 404

    claim_row = claim_rows.iloc[0]
    patient_id = claim_row.get("patient_id")
    provider_id = claim_row.get("provider_id")

    patient_history = claim_history[claim_history["patient_id"] == patient_id].sort_values("admission_date", ascending=False)
    provider_history = claim_history[claim_history["provider_id"] == provider_id].sort_values("admission_date", ascending=False)

    audit_result = {
        "status": claim_row.get("decision"),
        "rule_triggered": claim_row.get("rule_triggered") or "Not available",
        "explanation": claim_row.get("explanation") or "No detailed explanation is available for this claim.",
        "reasons": [reason for reason in str(claim_row.get("decision_reasons", "")).split(";") if reason],
    }

    return jsonify({
        "claim_id": claim_id,
        "patient_profile": {
            "patient_id": patient_id,
            "patient_name": _mock_patient_name(str(patient_id)),
            "history_count": int(patient_history.shape[0]),
            "recent_claims": _summary_records(patient_history.head(5), ["claim_id", "admission_date", "provider_id", "decision"]),
        },
        "provider_profile": {
            "provider_id": provider_id,
            "provider_name": _mock_provider_name(str(provider_id)),
            "recent_claim_volume": int(provider_history.shape[0]),
            "recent_claims": _summary_records(provider_history.head(5), ["claim_id", "admission_date", "patient_id", "decision"]),
        },
        "claim_details": {
            "claim_id": claim_row.get("claim_id"),
            "admission_date": claim_row.get("admission_date"),
            "discharge_date": claim_row.get("discharge_date"),
            "diagnosis_code": claim_row.get("diagnosis_code"),
            "procedure_code": claim_row.get("procedure_code"),
            "procedure_codes": claim_row.get("procedure_codes"),
            "billed_amount": claim_row.get("billed_amount"),
            "claim_type": claim_row.get("claim_type"),
        },
        "fraud_audit": audit_result,
    })

@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("index.html")

@app.route("/provider-summary", methods=["GET"])
def provider_summary():
    history_df = get_historical_claims()
    if history_df.empty:
        return jsonify({"providers": []})
        
    history_df["billed_amount"] = history_df["billed_amount"].astype(float).fillna(0)
    groups = history_df.groupby("provider_id")
    summary = []
    for provider_id, group in groups:
        summary.append({
            "provider_id": provider_id,
            "avg_amount": float(group["billed_amount"].mean()),
            "claim_count": len(group),
            "unique_patients": group["patient_id"].nunique(),
            "network": group["network"].mode().iloc[0] if not group["network"].mode().empty else "unknown",
        })
    summary = sorted(summary, key=lambda item: item["avg_amount"], reverse=True)
    return jsonify({"providers": summary})

@app.route("/audit-trail", methods=["GET"])
def audit_trail():
    history_df = get_historical_claims()
    if history_df.empty:
        return jsonify({"audit_chain": []})
    
    # Return last 50 claims as audit chain mock
    recent = history_df.tail(50).fillna("").to_dict(orient="records")
    return jsonify({"audit_chain": recent})

@app.route("/health", methods=["GET"])
def health_check():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM claims_history")
    count = cursor.fetchone()[0]
    conn.close()
    return jsonify({"status": "ok", "history_rows": count})

if __name__ == "__main__":
    # Debug mode disabled for security
    app.run(debug=False, port=5000)
