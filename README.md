# Real-Time Healthcare Insurance Fraud Detection

This project is a prototype for real-time healthcare insurance claim validation. It detects suspicious claims before payout, identifies provider-level patterns, and preserves a tamper-proof audit trail for decisions.

## Features
- real-time claim scoring at submission
- duplicate billing and ghost procedure detection
- anomaly-based provider and claim risk assessment
- fast-track approval for low-risk claims
- audit trail with cryptographic evidence for each decision

## Files
- `app.py` - Flask API for submitting claims and reviewing risk summaries
- `model.py` - fraud scoring and anomaly detection logic
- `data_generator.py` - synthetic claim dataset generator and loader
- `requirements.txt` - Python dependencies

## Quick Start
1. Create and activate a Python environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the API:
   ```bash
   python app.py
   ```
4. Submit claims to `http://127.0.0.1:5000/submit-claim`

## API Endpoints
- `POST /submit-claim` - submit a claim JSON body and receive risk score, verdict, and audit evidence
- `GET /provider-summary` - review provider risk summaries and anomaly metrics
- `GET /audit-trail` - retrieve the tamper-proof chain of claim decisions
- `GET /health` - check service health
- `GET /dashboard` - view the statistical dashboard and analytics UI

## Design Notes
The system combines historical pattern scoring, anomaly detection, and rule-based checks to catch fraud before reimbursement while fast-tracking genuine claims.
