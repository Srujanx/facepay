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
    password: str = Field(..., min_length=1)
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
    Create profiles row and Stripe customer. Send user_id in JSON body; no Authorization required.
    If a profile already exists for this user_id, return existing stripe_customer_id. Otherwise insert.
    """
    try:
        if not stripe.api_key:
            raise HTTPException(
                status_code=500,
                detail="STRIPE_SECRET_KEY not configured",
            )

        # Check if profile already exists
        try:
            result = (
                supabase.table("profiles")
                .select("stripe_customer_id")
                .eq("id", body.user_id)
                .execute()
            )
        except Exception as e:
            print(f"REGISTER ERROR (fetch profile): {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch profile")

        if result.data and len(result.data) > 0:
            existing = result.data[0]
            scid = existing.get("stripe_customer_id") if isinstance(existing, dict) else None
            stripe_customer_id = str(scid) if scid else ""
            return RegisterResponse(
                user_id=body.user_id,
                stripe_customer_id=stripe_customer_id,
            )

        # No row exists: create Supabase auth user first, then Stripe customer and profile
        real_user_id = None
        try:
            auth_response = supabase.auth.admin.create_user(
                {
                    "email": body.email,
                    "password": body.password,
                    "email_confirm": True,
                    "user_metadata": {"full_name": body.full_name},
                }
            )
            auth_user = getattr(auth_response, "user", None) if auth_response else None
            if auth_user is None and isinstance(auth_response, dict):
                auth_user = auth_response.get("user")
            if auth_user is not None:
                real_user_id = getattr(auth_user, "id", None) or (auth_user.get("id") if isinstance(auth_user, dict) else None)
            if real_user_id is not None:
                real_user_id = str(real_user_id)
        except Exception as e:
            print(f"REGISTER ERROR (create auth user): {e}")
            err = str(e).lower()
            if "already" in err or "duplicate" in err or "exists" in err:
                # Email already exists: look up existing user by email and use their id
                try:
                    list_res = supabase.auth.admin.list_users(per_page=1000)
                    users = getattr(list_res, "users", []) if list_res else []
                    if not isinstance(users, list):
                        users = []
                    existing_user = next(
                        (u for u in users if (getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)) == body.email),
                        None,
                    )
                    if existing_user:
                        existing_id = getattr(existing_user, "id", None) or (existing_user.get("id") if isinstance(existing_user, dict) else None)
                        if existing_id:
                            real_user_id = str(existing_id)
                            # If profile already exists for this user, return it
                            prof = supabase.table("profiles").select("stripe_customer_id").eq("id", real_user_id).execute()
                            if prof.data and len(prof.data) > 0:
                                row0 = prof.data[0]
                                scid = row0.get("stripe_customer_id") if isinstance(row0, dict) else None
                                return RegisterResponse(user_id=real_user_id, stripe_customer_id=str(scid) if scid else "")
                except Exception as lookup_err:
                    print(f"REGISTER ERROR (lookup existing user): {lookup_err}")
                    raise HTTPException(status_code=500, detail="Failed to create user")
            if real_user_id is None:
                raise HTTPException(status_code=500, detail="Failed to create user")

        if not real_user_id:
            print(f"REGISTER ERROR (create auth user): unexpected response")
            raise HTTPException(status_code=500, detail="Failed to create user")

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

        row = {
            "id": real_user_id,
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
            print(f"REGISTER ERROR (create profile): {e}")
            raise HTTPException(status_code=500, detail="Failed to create profile")

        return RegisterResponse(
            user_id=real_user_id,
            stripe_customer_id=customer.id,
        )
    except Exception as e:
        print(f"REGISTER ERROR: {e}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Registration failed")
