"""Attribution & permission manifest validation. An entry is rejected unless permissions are explicit."""
REQUIRED = ("source", "source_id", "title", "artist", "license", "attribution", "source_url", "file", "permissions")
PERMS = ("analysis", "playback", "storage")
FORBIDDEN_SOURCES = {"spotify", "youtube", "apple_music", "soundcloud_stream"}


def validate_entry(e: dict) -> list[str]:
    errs = [f"missing field: {k}" for k in REQUIRED if not e.get(k)]
    if e.get("source", "").lower() in FORBIDDEN_SOURCES:
        errs.append(f"source '{e['source']}' is not allowed as an analysis source")
    perms = e.get("permissions") or {}
    for p in PERMS:
        if not isinstance(perms.get(p), bool):
            errs.append(f"permissions.{p} must be an explicit true/false")
    if perms.get("analysis") and not (e.get("permission_evidence") or "").strip():
        errs.append("permission_evidence (URL or note showing where permission was verified) is required to enable analysis")
    if perms.get("analysis") and not perms.get("storage"):
        errs.append("analysis requires storage permission (audio is processed from private object storage)")
    if e.get("excerpt_only"):
        errs.append("excerpt-only audio can't demonstrate arbitrary trimming; use a verified full-length recording")
    return errs
