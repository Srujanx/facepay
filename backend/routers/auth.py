"""
POST /auth/register — create profile and Stripe customer after Supabase signUp.
No Authorization header required. Client sends user_id (from session.user.id after signUp)
plus email, full_name, fare_category in the JSON body. Optional pin (4 digits) sets pin_hash for /pay/pin-confirm.
"""
import hashlib
import os
import uuid
from datetime import date
from typing import Optional

import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from db.supabase_client import supabase

# Stripe: set from env (e.g. STRIPE_SECRET_KEY)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PIN_HASH_SECRET = os.getenv("PIN_HASH_SECRET", "facepay-pin-secret-change-in-production")

router = APIRouter()

FARE_CATEGORIES = frozenset(
    {"adult", "senior", "youth", "child", "u_pass", "tap", "armed_forces"}
)
INSTITUTIONS = frozenset({"durham_college", "ontario_tech", "trent_durham"})


class RegisterBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    fare_category: str = Field(..., min_length=1)
    pass_expires_at: Optional[date] = None
    institution: Optional[str] = None
    pin: Optional[str] = Field(None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def check_fare_institution_and_user_id(self):
        try:
            uuid.UUID(self.user_id)
        except ValueError:
            raise ValueError("user_id must be a valid UUID")
        if self.fare_category not in FARE_CATEGORIES:
            raise ValueError(
                f"fare_category must be one of {sorted(FARE_CATEGORIES)}"
            )
        if self.institution is not None and self.institution not in INSTITUTIONS:
            raise ValueError(
                f"institution must be one of {sorted(INSTITUTIONS)} or null"
            )
        return self


class RegisterResponse(BaseModel):
    user_id: str
    stripe_customer_id: str


@router.get("/register")
def register_get():
    """This endpoint is POST only. Use POST with JSON body: user_id, email, full_name, fare_category."""
    raise HTTPException(
        status_code=405,
        detail="Method Not Allowed. Use POST with JSON body: user_id, email, full_name, fare_category.",
    )


@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterBody):
    """
    Create profiles row and Stripe customer. Call after supabase.auth.signUp().
    Send user_id from session.user.id; no Authorization header required.
    """
    if not stripe.api_key:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_SECRET_KEY not configured",
        )

    # Create Stripe customer
    try:
        customer = stripe.Customer.create(
            email=body.email,
            name=body.full_name,
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    pin_hash = None
    if body.pin:
        pin_hash = hashlib.sha256((PIN_HASH_SECRET + body.pin).encode()).hexdigest()

    # Insert profile (id = auth.users.id from signUp)
    row = {
        "id": body.user_id,
        "full_name": body.full_name,
        "stripe_customer_id": customer.id,
        "fare_category": body.fare_category,
        "pass_expires_at": body.pass_expires_at.isoformat()
        if body.pass_expires_at
        else None,
        "institution": body.institution,
        "pin_hash": pin_hash,
    }
    try:
        supabase.table("profiles").insert(row).execute()
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "violates" in err:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            )
        raise HTTPException(status_code=500, detail="Failed to create profile")

    return RegisterResponse(
        user_id=body.user_id,
        stripe_customer_id=customer.id,
    )
