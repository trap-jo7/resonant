"""Decoding and conventional musical features (FFmpeg + librosa)."""
import subprocess
import numpy as np
import librosa

EMBED_SR = 48000   # sample rate expected by the CLAP checkpoint (verify on the model card)
FEAT_SR = 22050
HOP = 512
CHROMA_FPS = 2.0


def decode(path: str, timeout: int = 120) -> np.ndarray:
    """Decode to mono float32 @48 kHz using FFmpeg (argument list, no shell, hard timeout)."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-vn", "-ac", "1", "-ar", str(EMBED_SR), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    if p.returncode != 0 or not p.stdout:
        raise ValueError("Audio decoding failed; the file may be corrupt.")
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def peaks(y: np.ndarray, n: int = 2000) -> list[float]:
    """Max-abs peaks, normalised to [0,1], for the waveform display (real audio, not synthetic)."""
    if len(y) == 0:
        return []
    edges = np.linspace(0, len(y), n + 1, dtype=int)
    p = np.array([np.max(np.abs(y[a:b])) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
    m = p.max() or 1.0
    return [round(float(v / m), 4) for v in p]


def _unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def segment_features(y48: np.ndarray) -> dict:
    """Features for one section. Descriptors are scaled with fixed ranges to [0,1] (documented heuristic)."""
    y = librosa.resample(y48, orig_sr=EMBED_SR, target_sr=FEAT_SR)
    chroma = librosa.feature.chroma_cqt(y=y, sr=FEAT_SR, hop_length=2048)           # (12, T) ~10.8 fps
    step = max(1, int(round((FEAT_SR / 2048) / CHROMA_FPS)))
    T = chroma.shape[1] // step * step
    seq = chroma[:, :T].reshape(12, -1, step).mean(axis=2).T if T else chroma.T[:1]  # (N, 12) at ~2 Hz
    seq = np.array([_unit(f) for f in seq])
    mean = _unit(chroma.mean(axis=1))
    p = seq / (seq.sum(axis=1, keepdims=True) + 1e-9)
    entropy = -(p * np.log(p + 1e-9)).sum(axis=1) / np.log(12)
    chroma_conf = float(np.clip(1.0 - entropy.mean(), 0, 1))   # peaky pitch-class profile => more tonal evidence

    oenv = librosa.onset.onset_strength(y=y, sr=FEAT_SR, hop_length=HOP)
    tempo = float(np.atleast_1d(librosa.feature.rhythm.tempo(onset_envelope=oenv, sr=FEAT_SR, hop_length=HOP))[0])
    ac = librosa.autocorrelate(oenv - oenv.mean())
    lag = int(round(60.0 / max(tempo, 1) * FEAT_SR / HOP))
    tempo_conf = float(np.clip(ac[lag] / ac[0], 0, 1)) if 0 < lag < len(ac) and ac[0] > 0 else 0.0
    dur = len(y) / FEAT_SR
    onset_density = float(len(librosa.onset.onset_detect(onset_envelope=oenv, sr=FEAT_SR, hop_length=HOP)) / max(dur, 1e-6))

    rms = librosa.feature.rms(y=y)[0]
    rms_db = float(np.clip((20 * np.log10(rms.mean() + 1e-9) + 60) / 60, 0, 1))
    cent = float(np.clip(librosa.feature.spectral_centroid(y=y, sr=FEAT_SR).mean() / (FEAT_SR / 2), 0, 1))
    bw = float(np.clip(librosa.feature.spectral_bandwidth(y=y, sr=FEAT_SR).mean() / (FEAT_SR / 4), 0, 1))
    roll = float(np.clip(librosa.feature.spectral_rolloff(y=y, sr=FEAT_SR).mean() / (FEAT_SR / 2), 0, 1))
    flat = float(np.clip(librosa.feature.spectral_flatness(y=y).mean() * 10, 0, 1))
    return {"chroma_mean": mean.tolist(), "chroma_seq": np.round(seq, 4).tolist(), "chroma_conf": chroma_conf,
            "tempo": tempo, "tempo_conf": tempo_conf, "onset_density": onset_density,
            "timbre": [rms_db, cent, bw, roll, flat]}
