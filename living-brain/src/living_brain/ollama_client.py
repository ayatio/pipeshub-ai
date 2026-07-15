"""Minimal Ollama HTTP client built on urllib (no third-party deps).

Every call degrades gracefully: if Ollama is unreachable or returns an error,
the caller receives ``None`` and can fall back to a local implementation.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local URL)
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError):
        return None


def is_available(base_url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — any failure means "not available"
        return False


def embed(base_url: str, model: str, text: str, timeout: float = 30.0) -> list[float] | None:
    """Return an embedding for ``text`` or None if Ollama can't provide one."""
    # Newer Ollama exposes /api/embed ({"input": ...}); older exposes
    # /api/embeddings ({"prompt": ...}). Try the modern route first.
    res = _post(base_url + "/api/embed", {"model": model, "input": text}, timeout)
    if res and isinstance(res.get("embeddings"), list) and res["embeddings"]:
        return [float(x) for x in res["embeddings"][0]]
    res = _post(base_url + "/api/embeddings", {"model": model, "prompt": text}, timeout)
    if res and isinstance(res.get("embedding"), list):
        return [float(x) for x in res["embedding"]]
    return None


def generate(base_url: str, model: str, prompt: str, timeout: float = 120.0) -> str | None:
    """Return an LLM completion for ``prompt`` or None on failure."""
    res = _post(
        base_url + "/api/generate",
        {"model": model, "prompt": prompt, "stream": False},
        timeout,
    )
    if res and isinstance(res.get("response"), str):
        return res["response"].strip()
    return None
