from __future__ import annotations

import hashlib
import math
import re


class EmbeddingUnavailableError(RuntimeError):
    pass


def deterministic_embedding(text: str, dimensions: int = 256) -> list[float]:
    """Offline, deterministic feature hashing used as a no-download semantic baseline."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[\w'-]+", text.casefold())
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1 if digest[4] & 1 else -1
        vector[slot] += float(sign)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))
