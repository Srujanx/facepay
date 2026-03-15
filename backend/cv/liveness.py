"""
Liveness detection: interactive (blink/smile) for registration, passive (motion + texture) for terminal.
Interactive uses MediaPipe Face Mesh; passive uses frame-delta and texture analysis.
"""
from typing import Union

import cv2
import numpy as np

# -----------------------------------------------------------------------------
# Interactive (registration) — blink and smile, 10s timeout per challenge is caller's responsibility
# -----------------------------------------------------------------------------

# Tune during testing. Lower = more sensitive to blink (closed eye).
EAR_BLINK_THRESHOLD = 0.2

# MediaPipe Face Mesh eye landmark indices (left and right) for EAR.
# EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||) — vertical / horizontal.
LEFT_EYE_INDICES = (33, 160, 158, 133, 159, 157)   # p1..p6 for left eye
RIGHT_EYE_INDICES = (362, 385, 387, 263, 386, 384)

# Mouth landmarks: corners 61, 291; upper lip 13, lower lip 14.
MOUTH_CORNER_LEFT = 61
MOUTH_CORNER_RIGHT = 291
MOUTH_UPPER = 13
MOUTH_LOWER = 14
# Smile: mouth aspect ratio (openness / width) above this suggests smile.
MAR_SMILE_THRESHOLD = 0.12


def _ensure_rgb(img: Union[bytes, np.ndarray]) -> np.ndarray:
    """Decode bytes to image or convert BGR to RGB. MediaPipe expects RGB."""
    if isinstance(img, bytes):
        arr = np.frombuffer(img, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    elif img.shape[2] == 3:
        # Assume BGR from OpenCV
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def _ear_from_landmarks(landmarks, indices: tuple) -> float:
    """Eye Aspect Ratio for one eye. Indices: (p1, p2, p3, p4, p5, p6)."""
    p1, p2, p3, p4, p5, p6 = indices
    lm = landmarks.landmark

    def dist(a: int, b: int) -> float:
        la, lb = lm[a], lm[b]
        return ((la.x - lb.x) ** 2 + (la.y - lb.y) ** 2) ** 0.5

    vertical = dist(p2, p6) + dist(p3, p5)
    horizontal = 2.0 * dist(p1, p4)
    if horizontal <= 0:
        return 1.0
    return vertical / horizontal


def detect_blink(frame: Union[bytes, np.ndarray]) -> bool:
    """
    True if a blink is detected (eye closed). Uses MediaPipe EAR < 0.2.
    Caller should enforce 10s timeout and reset on timeout.
    """
    try:
        import mediapipe as mp
    except ImportError:
        raise ImportError("mediapipe is required for detect_blink; pip install mediapipe")

    img = _ensure_rgb(frame)
    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        min_detection_confidence=0.5,
    )
    results = face_mesh.process(img)
    face_mesh.close()

    if not results.multi_face_landmarks:
        return False

    landmarks = results.multi_face_landmarks[0]
    ear_left = _ear_from_landmarks(landmarks, LEFT_EYE_INDICES)
    ear_right = _ear_from_landmarks(landmarks, RIGHT_EYE_INDICES)
    min_ear = min(ear_left, ear_right)
    return min_ear < EAR_BLINK_THRESHOLD


def detect_smile(frame: Union[bytes, np.ndarray]) -> bool:
    """
    True if a smile is detected (lip corners up / mouth open). Uses MediaPipe mouth landmarks.
    Caller should enforce 10s timeout and reset on timeout.
    """
    try:
        import mediapipe as mp
    except ImportError:
        raise ImportError("mediapipe is required for detect_smile; pip install mediapipe")

    img = _ensure_rgb(frame)
    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        min_detection_confidence=0.5,
    )
    results = face_mesh.process(img)
    face_mesh.close()

    if not results.multi_face_landmarks:
        return False

    lm = results.multi_face_landmarks[0].landmark
    # Mouth aspect ratio: vertical openness / horizontal width
    mouth_width = abs(lm[MOUTH_CORNER_RIGHT].x - lm[MOUTH_CORNER_LEFT].x)
    mouth_height = abs(lm[MOUTH_LOWER].y - lm[MOUTH_UPPER].y)
    if mouth_width <= 0:
        return False
    mar = mouth_height / mouth_width
    return mar >= MAR_SMILE_THRESHOLD


# -----------------------------------------------------------------------------
# Passive (terminal) — frame-delta motion + texture; no user interaction
# -----------------------------------------------------------------------------

# Tune during testing: real face has micro-movement; static photo has near-zero.
# If mean absolute diff summed over 3 frames is below this, treat as static (spoof).
MOTION_THRESHOLD = 500.0

# Laplacian variance: real skin has moderate texture; smooth print may be very low.
# Repeating LCD grid can produce high variance; we accept a range.
TEXTURE_MIN_VAR = 50.0
TEXTURE_MAX_VAR = 50000.0


def _motion_score(frames: list[np.ndarray]) -> float:
    """Sum of mean absolute differences between consecutive frames (grayscale)."""
    if len(frames) < 2:
        return 0.0
    total = 0.0
    for i in range(len(frames) - 1):
        g1 = frames[i] if frames[i].ndim == 2 else cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
        g2 = frames[i + 1] if frames[i + 1].ndim == 2 else cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(g1, g2)
        total += float(np.mean(diff))
    return total


def _texture_score(frame: np.ndarray) -> float:
    """Laplacian variance of center crop (face region). Real skin has irregular texture."""
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Use center 60% to avoid borders
    margin_w, margin_h = int(0.2 * w), int(0.2 * h)
    crop = gray[margin_h : h - margin_h, margin_w : w - margin_w]
    if crop.size == 0:
        return 0.0
    lap = cv2.Laplacian(crop, cv2.CV_64F, ksize=3)
    return float(lap.var())


def check_passive_liveness(frames: list[Union[bytes, np.ndarray]]) -> bool:
    """
    Returns True if the frames look like a live face (motion + texture pass).
    Returns False for static photos or screens (spoofing).
    Expects 3–5 consecutive frames (e.g. from terminal camera loop).
    """
    if len(frames) < 2:
        return False

    # Decode bytes to numpy if needed
    imgs: list[np.ndarray] = []
    for f in frames:
        if isinstance(f, bytes):
            arr = np.frombuffer(f, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return False
            imgs.append(img)
        else:
            imgs.append(f)

    motion = _motion_score(imgs)
    if motion < MOTION_THRESHOLD:
        return False

    # Texture on middle frame
    mid = imgs[len(imgs) // 2]
    texture = _texture_score(mid)
    if texture < TEXTURE_MIN_VAR or texture > TEXTURE_MAX_VAR:
        return False

    return True
