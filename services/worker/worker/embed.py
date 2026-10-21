"""Replaceable audio-embedding interface; initial implementation = a music-capable CLAP checkpoint.

Checkpoint requirements (verify against the model card of CLAP_MODEL before pinning CLAP_REVISION):
  * mono audio at 48 kHz
  * the model sees ~10 s per input, so longer sections are split into <=10 s chunks and the
    chunk embeddings are L2-normalised, averaged and re-normalised.
"""
from typing import Protocol
import numpy as np
from resonant_common.config import settings

CHUNK_S = 10
SR = 48000


class Embedder(Protocol):
    name: str
    dim: int
    def embed(self, y48: np.ndarray) -> np.ndarray: ...


class ClapEmbedder:
    def __init__(self):
        import torch
        from transformers import ClapModel, ClapProcessor
        self.torch = torch
        self.name = settings.model_version
        self.dim = settings.embed_dim
        self.model = ClapModel.from_pretrained(settings.clap_model, revision=settings.clap_revision).eval()
        self.proc = ClapProcessor.from_pretrained(settings.clap_model, revision=settings.clap_revision)

    def embed(self, y48: np.ndarray) -> np.ndarray:
        n = CHUNK_S * SR
        chunks = [y48[i:i + n] for i in range(0, len(y48), n)]
        if len(chunks) > 1 and len(chunks[-1]) < 2 * SR:   # drop a tiny tail instead of padding it
            chunks.pop()
        try:
            inputs = self.proc(audio=chunks, sampling_rate=SR, return_tensors="pt")
        except TypeError:                                   # older transformers used `audios=`
            inputs = self.proc(audios=chunks, sampling_rate=SR, return_tensors="pt")
        with self.torch.inference_mode():
            feats = self.model.get_audio_features(**inputs).cpu().numpy()
        feats = feats / (np.linalg.norm(feats, axis=1, keepdims=True) + 1e-9)
        v = feats.mean(axis=0)
        v = (v / (np.linalg.norm(v) + 1e-9)).astype(np.float32)
        if v.shape[0] != self.dim:
            raise RuntimeError(f"Embedding dim {v.shape[0]} != EMBED_DIM {self.dim}; update the schema and EMBED_DIM.")
        return v


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Kept warm for the life of the worker process."""
    global _embedder
    if _embedder is None:
        _embedder = ClapEmbedder()
    return _embedder
