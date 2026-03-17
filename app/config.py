import os

def get_config():
    return {
        "ml_url": os.environ.get("ML_URL", "http://immich-machine-learning:3003"),
        "face_model": os.environ.get("FACE_MODEL", "buffalo_l"),
        "face_min_score": float(os.environ.get("FACE_MIN_SCORE", "0.5")),
        "max_recognition_distance": float(os.environ.get("MAX_RECOGNITION_DISTANCE", "0.6")),
        "ml_timeout_seconds": float(os.environ.get("ML_TIMEOUT_SECONDS", "120")),
        "db": {
            "host": os.environ.get("DB_HOSTNAME", "database"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USERNAME", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_DATABASE_NAME", "immich"),
        },
    }
