# ForNebius — Nebius × NVIDIA Global AI Hackathon working folder

Deadline: Fri Oct 30, 2026, 10:00 AM PT (1:00 PM ET). Target submit: Tue Oct 28.
Plan: Project doc `claude/hackathon-plan-nebius-nvidia-2026-10-09.md`.

## Done (2026-10-09)
- Registered on Devpost (solo, org: LexProof Solutions).
- Applied to the Nebius Builder Program (pgskannan@gmail.com).
- Submitted the Token Factory promo form (activation code NEBIUS-DEVPOST-GLOBAL26). The $25 code arrives by email.

## Spike (Part A): go/no-go
1. Sign up at https://tokenfactory.nebius.com, redeem the emailed promo code (Billing / promo codes), and create an API key.
2. Add this line to `backend\.env` (already gitignored):
   `NEBIUS_API_KEY=<your key>`
3. From `C:\Projects\LexProof` in PowerShell:
   ```
   .\backend\.venv\Scripts\python.exe ForNebius\nebius_spike.py --list-only
   .\backend\.venv\Scripts\python.exe ForNebius\nebius_spike.py --with-gemini
   ```
4. Results go to `ForNebius\spike_out\results.md`, with the raw output for each model/contract alongside.

The script uses only packages already in the backend venv (httpx, jsonschema, python-docx, python-dotenv).
It sends LexProof's production analysis prompt for CONTRACT_01 and CONTRACT_03 to every Nemotron text model
your key can use. It tries strict json_schema first, then falls back to json_object, validates the output
against the production ANALYSIS_RESPONSE_SCHEMA, and compares the result with the Gemini baseline. The
playbook is left empty, because it lives in Firestore.

Go = at least one Nemotron model returns schema-valid output on both contracts with findings comparable to Gemini's.
