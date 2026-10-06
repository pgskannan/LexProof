"""Public payment chain on the verification app. No auth, no PayPal payloads."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..repositories.firestore import FirestoreRepository
from ..services.paypal.public_chain import public_payment_chain

router = APIRouter(tags=["public-verification"])


@router.get("/contracts/{passport_id}/payments")
def public_contract_payments(passport_id: str) -> dict:
    chain = public_payment_chain(
        passport_id,
        passports=FirestoreRepository("legal_passports"),
        obligations=FirestoreRepository("payment_obligations"),
        receipts=FirestoreRepository("payment_receipts"),
        settings=FirestoreRepository("payment_settings"),
        anchors=FirestoreRepository("evidence_anchors"),
        checkpoints=FirestoreRepository("payment_checkpoints"),
    )
    if chain is None:
        raise HTTPException(status_code=404, detail="Passport not found")
    return chain
