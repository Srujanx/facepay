"""
Face embedding generation using DeepFace (Facenet model, 128-dim vectors).
All operations in memory — no images written to disk.
"""
import base64
from typing import Optional, Union

import cv2
import numpy as np
from deepface import DeepFace

# Facenet produces 128-dim embeddings (see APP_FLOW.md / schema)
MODEL_NAME = "Facenet"


def _decode_frame(frame: Union[bytes, str]) -> Optional[np.ndarray]:
    """
    Decode base64 image bytes to BGR numpy array for DeepFace.
    Accepts base64-encoded bytes or str. Returns None on decode error.
    """
    try:
        if isinstance(frame, str):
            raw = base64.b64decode(frame)
        else:
            raw = base64.b64decode(frame)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        return img  # BGR, as expected by DeepFace
    except Exception:
        return None


def _embed_frame(img: np.ndarray) -> Optional[list[float]]:
    """
    Get 128-dim embedding for one BGR image. Returns None if no face detected.
    """
    try:
        result = DeepFace.represent(
            img_path=img,
            model_name=MODEL_NAME,
            enforce_detection=False,
            detector_backend="opencv",
            align=True,
        )
        if not result or not isinstance(result, list):
            return None
        # Take first detected face
        first = result[0]
        embedding = first.get("embedding")
        if embedding is None or not isinstance(embedding, (list, np.ndarray)):
            return None
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return list(embedding)
    except Exception:
        return None


def generate_embedding(frames: list[Union[bytes, str]]) -> Optional[list[float]]:
    """
    Average 128-dim face embedding across multiple base64-encoded frames (e.g. 5 from registration).
    Uses Facenet model. Skips frames where no face is detected.
    Returns None if no face found in any frame.
    """
    if not frames:
        return None

    embeddings: list[list[float]] = []

    for frame in frames:
        img = _decode_frame(frame)
        if img is None:
            continue
        emb = _embed_frame(img)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        return None

    averaged = np.mean(embeddings, axis=0)
    return averaged.tolist()


def extract_embedding_from_frame(frame: Union[bytes, str]) -> Optional[list[float]]:
    """
    Single-frame 128-dim encoding for terminal identification.
    Accepts base64-encoded image bytes or str. Returns None if no face detected.
    """
    img = _decode_frame(frame)
    if img is None:
        return None
    return _embed_frame(img)
