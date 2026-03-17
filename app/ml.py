import json
import logging
import httpx
from typing import Any

from .config import get_config

logger = logging.getLogger(__name__)


def _parse_embedding(emb: Any) -> list[float] | None:
    """Normalize ML embedding to list[float]. ML may return list or JSON string."""
    if isinstance(emb, list):
        if not emb:
            return None
        try:
            return [float(x) for x in emb]
        except (TypeError, ValueError):
            return None
    if isinstance(emb, str):
        try:
            parsed = json.loads(emb)
            if isinstance(parsed, list):
                return [float(x) for x in parsed]
            return None
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        try:
            return [float(x.strip()) for x in emb.split(",") if x.strip()]
        except (ValueError, AttributeError):
            return None
    return None


def detect_faces(image_bytes: bytes, content_type: str) -> list[dict[str, Any]]:
    """Call Immich ML /predict for facial-recognition; return list of { boundingBox, score, embedding }.
    Ensures each face has 'embedding' as list[float] (ML may return list or string).
    """
    cfg = get_config()
    entries = {
        "facial-recognition": {
            "recognition": {"modelName": cfg["face_model"]},
            "detection": {
                "modelName": cfg["face_model"],
                "options": {"minScore": cfg["face_min_score"]},
            },
        }
    }
    timeout = cfg["ml_timeout_seconds"]
    url = f"{cfg['ml_url'].rstrip('/')}/predict"
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            data={"entries": json.dumps(entries)},
            files={"image": ("image", image_bytes, content_type or "image/jpeg")},
        )
        response.raise_for_status()
    data = response.json()
    faces = data.get("facial-recognition")
    if not isinstance(faces, list):
        return []
    out: list[dict[str, Any]] = []
    for i, f in enumerate(faces):
        if not isinstance(f, dict):
            continue
        if i == 0:
            logger.info("detect_faces: first face keys %s", list(f.keys()))
        emb_raw = f.get("embedding")
        emb = _parse_embedding(emb_raw)
        if emb is not None:
            out.append({**f, "embedding": emb})
        else:
            logger.info("detect_faces: face %d embedding unparseable (type=%s)", i, type(emb_raw).__name__)
    return out
