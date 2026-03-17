import logging
import sys

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .config import get_config
from .db import find_person_name_for_embedding
from .ml import detect_faces

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logging.getLogger("app").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Face API", description="Upload image, get detected face names from Immich.")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail if isinstance(exc.detail, str) else str(exc.detail)},
    )


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.post("/detect")
async def detect(
    image: UploadFile = File(None, alias="image"),
    file: UploadFile = File(None, alias="file"),
) -> dict[str, list[str]]:
    """
    Accept an image upload (multipart form field: image or file).
    Returns {"names": ["Name1", "Name2", ...]} (or "Unknown" for unmatched faces).
    """
    upload = image or file
    if not upload:
        raise HTTPException(
            status_code=400,
            detail="Missing file. Send multipart form field 'image' or 'file'.",
        )
    if upload.content_type and upload.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}",
        )
    try:
        image_bytes = await upload.read()
    except Exception as e:
        logger.exception("Failed to read upload")
        raise HTTPException(status_code=400, detail="Failed to read image") from e
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        faces = detect_faces(image_bytes, upload.content_type or "image/jpeg")
    except Exception as e:
        logger.exception("ML predict failed")
        raise HTTPException(
            status_code=502,
            detail=f"Face detection failed: {e!s}",
        ) from e

    cfg = get_config()
    max_dist = cfg["max_recognition_distance"]
    logger.info("detect: ML returned %d face(s), lookup threshold=%.2f", len(faces), max_dist)
    names: list[str] = []
    for i, face in enumerate(faces):
        emb = face.get("embedding")
        if not isinstance(emb, list) or not emb:
            logger.info("detect: face %d -> Unknown (no embedding)", i)
            names.append("Unknown")
            continue
        try:
            name, reason = find_person_name_for_embedding(emb, max_dist)
            display = name if name is not None else "Unknown"
            logger.info("detect: face %d -> %s (%s)", i, display, reason)
            names.append(display if name is not None else "Unknown")
        except Exception as e:
            logger.exception("detect: face %d -> DB lookup failed: %s", i, e)
            names.append("Unknown")

    return {"names": names}
