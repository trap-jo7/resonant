"""Server-side media validation. Subprocesses use argument lists (no shell) plus time/CPU limits."""
import json
import resource
import subprocess

ALLOWED_EXT = {".mp3", ".wav", ".flac", ".m4a"}
ALLOWED_CODECS = {"mp3", "flac", "aac", "alac"} | {f"pcm_{x}" for x in
                  ("s16le", "s24le", "s32le", "f32le", "u8", "s16be", "s24be")}
CONTENT_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".m4a": "audio/mp4"}


class MediaError(ValueError):
    pass


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # validation never writes files


def _run(args: list[str], timeout: int):
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, preexec_fn=_limits, check=False)
    except subprocess.TimeoutExpired:
        raise MediaError("The file took too long to inspect. Try a shorter or simpler file.")


def probe(path: str, ext: str, max_duration_s: float) -> dict:
    if ext not in ALLOWED_EXT:
        raise MediaError("Unsupported file type. Use MP3, WAV, FLAC or M4A.")
    p = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
              "-select_streams", "a:0", path], 20)
    if p.returncode != 0:
        raise MediaError("This file couldn't be read as audio. It may be corrupt or not really audio.")
    info = json.loads(p.stdout or "{}")
    streams = info.get("streams") or []
    if not streams:
        raise MediaError("No audio stream found in this file.")
    codec = streams[0].get("codec_name", "")
    if codec not in ALLOWED_CODECS:
        raise MediaError(f"Unsupported audio codec ({codec or 'unknown'}). Use MP3, WAV, FLAC or M4A.")
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise MediaError("Couldn't determine the track duration.")
    if duration <= 0:
        raise MediaError("The audio appears to be empty.")
    if duration > max_duration_s:
        raise MediaError(f"Audio is longer than the {int(max_duration_s // 60)}-minute limit.")
    # Decode a few seconds to catch truncated/corrupt streams early (full decode happens in the worker).
    d = _run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-t", "5", "-f", "null", "-"], 30)
    if d.returncode != 0:
        raise MediaError("The audio couldn't be decoded. The file may be corrupt.")
    return {"duration_s": duration, "codec": codec}
