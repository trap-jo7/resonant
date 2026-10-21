import os
from dataclasses import dataclass, field


def _weights(name: str, default: str) -> dict:
    parts = [float(x) for x in os.environ.get(name, default).split(",")]
    assert len(parts) == 4, f"{name} needs 4 values"
    total = sum(parts)
    return dict(zip(("embedding", "harmonic", "rhythm", "timbre"), [p / total for p in parts]))


def _windows(raw: str):
    return [tuple(float(x) for x in pair.split(":")) for pair in raw.split(",")]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "postgresql://resonant_app:resonant_app@localhost:5432/resonant")
    database_owner_url: str = os.environ.get("DATABASE_OWNER_URL", "postgresql://resonant:resonant@localhost:5432/resonant")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    s3_endpoint: str = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
    s3_public_endpoint: str = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
    s3_access_key: str = os.environ.get("S3_ACCESS_KEY", "")
    s3_secret_key: str = os.environ.get("S3_SECRET_KEY", "")
    s3_bucket: str = os.environ.get("S3_BUCKET", "resonant-private")
    s3_region: str = os.environ.get("S3_REGION", "us-east-1")
    signed_url_ttl_s: int = int(os.environ.get("SIGNED_URL_TTL_S", "900"))
    max_upload_bytes: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    max_duration_s: float = float(os.environ.get("MAX_DURATION_S", "600"))
    retention_hours: int = int(os.environ.get("UPLOAD_RETENTION_HOURS", "24"))
    query_min_s: float = float(os.environ.get("QUERY_MIN_S", "5"))
    query_max_s: float = float(os.environ.get("QUERY_MAX_S", "60"))
    windows: tuple = field(default_factory=lambda: tuple(_windows(os.environ.get("WINDOWS", "12:6,24:12"))))
    preprocess_version: str = os.environ.get("PREPROCESS_VERSION", "pp1")
    clap_model: str = os.environ.get("CLAP_MODEL", "laion/larger_clap_music")
    clap_revision: str = os.environ.get("CLAP_REVISION", "main")
    embed_dim: int = int(os.environ.get("EMBED_DIM", "512"))
    weights: dict = field(default_factory=lambda: {
        "balanced": _weights("WEIGHTS_BALANCED", "0.45,0.30,0.15,0.10"),
        "vibe": _weights("WEIGHTS_VIBE", "0.60,0.05,0.20,0.15"),
        "harmony": _weights("WEIGHTS_HARMONY", "0.25,0.60,0.05,0.10"),
    })
    rate_per_min: int = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))
    upload_per_hour: int = int(os.environ.get("UPLOAD_LIMIT_PER_HOUR", "10"))
    analysis_per_hour: int = int(os.environ.get("ANALYSIS_LIMIT_PER_HOUR", "40"))
    enable_musicbrainz: bool = os.environ.get("ENABLE_MUSICBRAINZ", "false").lower() == "true"
    musicbrainz_ua: str = os.environ.get("MUSICBRAINZ_USER_AGENT", "")
    cors_origin: str = os.environ.get("CORS_ORIGIN", "http://localhost:3000")

    @property
    def model_version(self) -> str:
        return f"{self.clap_model}@{self.clap_revision}"


settings = Settings()
