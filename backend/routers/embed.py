"""
POST /embed — store 128-dim face embedding from 5 base64 JPEG frames.
Zero image data is persisted; only the embedding vector is written to face_embeddings.
"""
import base64
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from cv.embedder import generate_embedding
from db.supabase_client import supabase

router = APIRouter()

# Max 2MB per frame (decoded JPEG size)
MAX_FRAME_BYTES = 2 * 1024 * 1024
EXPECTED_FRAMES = 5


class EmbedBody(BaseModel):
    frames: list[str] = Field(..., min_length=1, max_length=10)
    user_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def check_user_id_and_frames(self):
        try:
            uuid.UUID(self.user_id)
        except ValueError:
            raise ValueError("user_id must be a valid UUID")
        for i, b64 in enumerate(self.frames):
            try:
                raw = base64.b64decode(b64, validate=True)
            except Exception:
                raise ValueError(f"frames[{i}] is not valid base64")
            if len(raw) > MAX_FRAME_BYTES:
                raise ValueError(
                    f"frames[{i}] exceeds max size ({MAX_FRAME_BYTES} bytes)"
                )
        return self


class EmbedResponse(BaseModel):
    embedding_id: str


@router.post("/embed", response_model=EmbedResponse)
def embed(body: EmbedBody):
    """
    Accept 5 base64-encoded JPEG frames, compute averaged 128-dim embedding,
    store in face_embeddings. Returns embedding_id. No images are stored.
    """
    embedding = generate_embedding(body.frames)
    if embedding is None:
        raise HTTPException(
            status_code=400,
            detail="No face detected in any frame. Ensure good lighting and one clear face.",
        )

    if len(embedding) != 128:
        raise HTTPException(
            status_code=500,
            detail="Embedding dimension mismatch",
        )

    row = {
        "user_id": body.user_id,
        "embedding": embedding,
    }
    try:
        result = supabase.table("face_embeddings").insert(row).execute()
    except Exception as e:
        err = str(e).lower()
        if "foreign key" in err or "violates" in err:
            raise HTTPException(
                status_code=404,
                detail="User not found. Complete registration first.",
            )
        raise HTTPException(
            status_code=500,
            detail="Failed to store embedding",
        )

    # Supabase returns inserted row(s) with id
    data = result.data
    if not data or len(data) == 0:
        raise HTTPException(
            status_code=500,
            detail="Failed to store embedding",
        )
    embedding_id = str(data[0]["id"])
    return EmbedResponse(embedding_id=embedding_id)
