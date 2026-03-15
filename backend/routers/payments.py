"""
POST /pay and POST /pay/pin-confirm — charge fare (or log $0) and insert transaction.
Supabase Realtime emits on INSERT so the terminal can show the success screen.
"""
import hashlib
import os
from typing import Optional

import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.supabase_client import supabase

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PIN_HASH_SECRET = os.getenv("PIN_HASH_SECRET", "facepay-pin-secret-change-in-production")


# ---------------------------------------------------------------------------
# POST /pay
# ---------------------------------------------------------------------------

class PayBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    amount_cents: int = Field(..., ge=0)
    route_id: str = Field(..., min_length=1)
    trip_id: Optional[str] = None
    stop_id: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    resolved_fare_category: str = Field(..., min_length=1)
    pass_was_expired: bool = False


class PayResponse(BaseModel):
    transaction_id: str
    status: str  # "success" | "payment_failed"


def _get_stripe_customer_id(user_id: str) -> Optional[str]:
    try:
        r = (
            supabase.table("profiles")
            .select("stripe_customer_id")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if r.data and len(r.data) > 0 and r.data[0].get("stripe_customer_id"):
            return r.data[0]["stripe_customer_id"]
    except Exception:
        pass
    return None


def _charge_and_log(
    user_id: str,
    amount_cents: int,
    route_id: str,
    trip_id: Optional[str],
    stop_id: Optional[str],
    confidence: float,
    resolved_fare_category: str,
    pass_was_expired: bool,
) -> tuple[str, str]:
    """
    If amount_cents > 0: create PaymentIntent (confirm=True, off_session=True).
    Insert transaction row (status success or payment_failed). Returns (transaction_id, status).
    """
    stripe_pi_id: Optional[str] = None
    status = "success"

    if amount_cents > 0:
        customer_id = _get_stripe_customer_id(user_id)
        if not customer_id:
            status = "payment_failed"
        else:
            try:
                pi = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency="cad",
                    customer=customer_id,
                    confirm=True,
                    off_session=True,
                    automatic_payment_methods={"enabled": True},
                )
                stripe_pi_id = pi.id if pi.status == "succeeded" else None
                if pi.status != "succeeded":
                    status = "payment_failed"
            except stripe.StripeError:
                stripe_pi_id = None
                status = "payment_failed"

    row = {
        "user_id": user_id,
        "amount_cents": amount_cents,
        "confidence": confidence,
        "stripe_pi_id": stripe_pi_id,
        "status": status,
        "resolved_fare_category": resolved_fare_category,
        "pass_was_expired": pass_was_expired,
        "route_id": route_id or None,
        "trip_id": trip_id or None,
        "stop_id": stop_id or None,
    }
    result = supabase.table("transactions").insert(row).execute()
    if not result.data or len(result.data) == 0:
        raise HTTPException(status_code=500, detail="Failed to log transaction")
    transaction_id = str(result.data[0]["id"])
    return transaction_id, status


@router.post("/", response_model=PayResponse)
def pay(body: PayBody):
    """
    Charge fare (or log $0). If amount_cents > 0, create Stripe PaymentIntent.
    Insert transaction; Supabase Realtime emits on INSERT.
    """
    if not stripe.api_key and body.amount_cents > 0:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_SECRET_KEY not configured",
        )
    transaction_id, status = _charge_and_log(
        user_id=body.user_id,
        amount_cents=body.amount_cents,
        route_id=body.route_id,
        trip_id=body.trip_id,
        stop_id=body.stop_id,
        confidence=body.confidence,
        resolved_fare_category=body.resolved_fare_category,
        pass_was_expired=body.pass_was_expired,
    )
    return PayResponse(transaction_id=transaction_id, status=status)


# ---------------------------------------------------------------------------
# POST /pay/pin-confirm
# ---------------------------------------------------------------------------

class PinConfirmBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    pin: str = Field(..., min_length=4, max_length=4)
    amount_cents: int = Field(..., ge=0)
    route_id: str = Field(..., min_length=1)
    trip_id: Optional[str] = None
    stop_id: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    resolved_fare_category: str = Field(..., min_length=1)
    pass_was_expired: bool = False


def _pin_hash(pin: str) -> str:
    return hashlib.sha256((PIN_HASH_SECRET + pin).encode()).hexdigest()


@router.post("/pin-confirm", response_model=PayResponse)
def pin_confirm(body: PinConfirmBody):
    """
    Verify PIN against profile pin_hash, then same charge + log flow as POST /pay.
    """
    try:
        r = (
            supabase.table("profiles")
            .select("pin_hash")
            .eq("id", body.user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch profile")

    if not r.data or len(r.data) == 0:
        raise HTTPException(status_code=404, detail="User not found")

    stored_hash = r.data[0].get("pin_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=400,
            detail="PIN not set for this account. Complete registration with PIN.",
        )

    if stored_hash != _pin_hash(body.pin):
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    if not stripe.api_key and body.amount_cents > 0:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_SECRET_KEY not configured",
        )

    transaction_id, status = _charge_and_log(
        user_id=body.user_id,
        amount_cents=body.amount_cents,
        route_id=body.route_id,
        trip_id=body.trip_id,
        stop_id=body.stop_id,
        confidence=body.confidence,
        resolved_fare_category=body.resolved_fare_category,
        pass_was_expired=body.pass_was_expired,
    )
    return PayResponse(transaction_id=transaction_id, status=status)
