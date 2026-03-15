"""
POST /identify — identify face from frame(s), run liveness, pgvector search, resolve_fare.
Accepts a single base64 frame (and optional liveness_frames for passive liveness) and route_id.
Returns user_id, full_name, confidence, fare_category, amount_cents, pass_expired, trip_id.
Confidence thresholds: >0.55 auto, 0.40–0.55 pin, <0.40 reject (DeepFace cosine similarity).
"""
import base64
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cv.embedder import extract_embedding_from_frame
from cv.liveness import check_passive_liveness
from db.supabase_client import supabase

router = APIRouter()

# Confidence thresholds — DeepFace cosine similarity (lower than face_recognition)
CONFIDENCE_AUTO = 0.55
CONFIDENCE_PIN_MIN = 0.40


class IdentifyBody(BaseModel):
    frame: str = Field(..., min_length=1)
    route_id: str = Field(..., min_length=1)
    liveness_frames: Optional[list[str]] = Field(None, min_length=3, max_length=5)


class IdentifyResponse(BaseModel):
    user_id: str
    full_name: str
    confidence: float
    fare_category: str
    amount_cents: int
    pass_expired: bool
    trip_id: Optional[str] = None
    confidence_tier: str  # "auto" | "pin" | "reject"


class IdentifyRejectResponse(BaseModel):
    matched: bool = False
    reason: str
    confidence: Optional[float] = None


@router.post("/identify")
def identify(body: IdentifyBody) -> IdentifyResponse | IdentifyRejectResponse:
    """
    Run passive liveness (if liveness_frames provided), generate embedding from frame,
    pgvector cosine search, resolve_fare(). Returns match + fare or reject reason.
    """
    # 1. Passive liveness (if 3+ frames provided)
    if body.liveness_frames and len(body.liveness_frames) >= 3:
        raw_frames = []
        for b64 in body.liveness_frames:
            try:
                raw_frames.append(base64.b64decode(b64, validate=True))
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid base64 in liveness_frames",
                )
        if not check_passive_liveness(raw_frames):
            return IdentifyRejectResponse(
                matched=False,
                reason="liveness_failed",
            )

    # 2. Generate embedding from frame
    embedding = extract_embedding_from_frame(body.frame)
    if embedding is None:
        return IdentifyRejectResponse(
            matched=False,
            reason="no_face_detected",
        )

    if len(embedding) != 128:
        raise HTTPException(
            status_code=500,
            detail="Embedding dimension mismatch",
        )

    # 3. pgvector cosine similarity search (match_face RPC)
    try:
        rpc_result = supabase.rpc(
            "match_face",
            {"query_embedding": embedding},
        ).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Match failed: {e}",
        )

    data = rpc_result.data
    if not data or len(data) == 0:
        return IdentifyRejectResponse(
            matched=False,
            reason="no_match",
            confidence=None,
        )

    row = data[0]
    user_id = str(row["user_id"])
    confidence = float(row["confidence"])
    print(f"IDENTIFY: confidence={confidence:.4f}, user_id={user_id}")

    # 4. Below 0.90 → reject (no identity returned)
    if confidence < CONFIDENCE_PIN_MIN:
        return IdentifyRejectResponse(
            matched=False,
            reason="low_confidence",
            confidence=confidence,
        )

    # 5. Fetch profile for full_name
    try:
        profile_result = (
            supabase.table("profiles")
            .select("full_name")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile fetch failed: {e}")

    profile_data = profile_result.data
    if not profile_data or len(profile_data) == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    full_name = profile_data[0]["full_name"]

    # 6. resolve_fare(user_id)
    try:
        fare_result = supabase.rpc(
            "resolve_fare",
            {"p_user_id": user_id},
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"resolve_fare failed: {e}")

    fare_data = fare_result.data
    if not fare_data or len(fare_data) == 0:
        raise HTTPException(status_code=500, detail="resolve_fare returned no row")

    fare = fare_data[0]
    resolved_category: str = fare["resolved_category"]
    amount_cents: int = int(fare["amount_cents"])
    pass_expired: bool = bool(fare["pass_expired"])

    # 7. Confidence tier
    if confidence > CONFIDENCE_AUTO:
        confidence_tier = "auto"
    elif confidence >= CONFIDENCE_PIN_MIN:
        confidence_tier = "pin"
    else:
        confidence_tier = "reject"

    # trip_id: from GTFS when available; for now null (wire in gtfs router later)
    trip_id: Optional[str] = None

    return IdentifyResponse(
        user_id=user_id,
        full_name=full_name,
        confidence=confidence,
        fare_category=resolved_category,
        amount_cents=amount_cents,
        pass_expired=pass_expired,
        trip_id=trip_id,
        confidence_tier=confidence_tier,
    )
