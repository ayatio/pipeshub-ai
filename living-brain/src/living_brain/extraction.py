"""Typed extraction from chunks (BUILD-BRIEF §2, §5, Phase 4).

A local LLM reads a chunk and returns STRICT JSON: typed entities and evidenced
relationships. The pure parts here — the prompt builder, the JSON parser, and
pydantic validation/normalisation — are unit-tested offline. The network call
(Ollama, with an optional cloud fallback for extraction only) runs under
`-m ollama`.

Constitution ties (§1): extraction never invents provenance — every produced
relationship carries the chunk's evidence text, and nothing is persisted here;
this module only proposes.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator

from .config import Config

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class ExtractedEntity(BaseModel):
    type: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    props: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _norm_type(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("entity type must be non-empty")
        return v

    @field_validator("label")
    @classmethod
    def _norm_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("entity label must be non-empty")
        return v


class ExtractedRelationship(BaseModel):
    source: str  # a label appearing in entities
    target: str  # a label appearing in entities
    rel_type: str
    evidence: str = ""

    @field_validator("source", "target", "rel_type")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("relationship fields must be non-empty")
        return v


class Extraction(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


_SCHEMA_HINT = (
    '{"entities":[{"type":"person|project|org|place|concept|...",'
    '"label":"Canonical Name","aliases":["..."],"props":{"key":"value"}}],'
    '"relationships":[{"source":"Label A","target":"Label B",'
    '"rel_type":"works-on|owns|located-in|...","evidence":"quote from text"}]}'
)


def build_prompt(text: str) -> str:
    """Build the strict-JSON extraction prompt for a single chunk."""
    return (
        "You extract a knowledge graph from a note. Return ONLY valid JSON, no "
        "prose, matching this shape:\n"
        f"{_SCHEMA_HINT}\n\n"
        "Rules: use canonical labels; put a short verbatim quote in each "
        "relationship's evidence; omit anything not supported by the text; if "
        "nothing is present return {\"entities\":[],\"relationships\":[]}.\n\n"
        "NOTE:\n"
        f"{text}\n"
    )


def parse_extraction(raw: str) -> Extraction:
    """Parse+validate a model's raw output into an Extraction.

    Tolerant of ```json fences; strict about structure. Raises ValueError on
    anything that isn't a valid extraction object (the caller decides whether to
    retry or fall back).
    """
    cleaned = _FENCE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extraction is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("extraction JSON must be an object")
    return Extraction.model_validate(data)


class Extractor:
    """Local-first extractor over Ollama, with an optional cloud fallback."""

    def __init__(self, cfg: Config | None = None, *, max_retries: int = 2) -> None:
        self.cfg = cfg or Config.load()
        self.max_retries = max_retries

    def _ollama(self, prompt: str) -> str:
        resp = httpx.post(
            f"{self.cfg.ollama_url}/api/generate",
            json={
                "model": self.cfg.model_extract,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def extract(self, text: str) -> Extraction:
        """Extract from one chunk. Retries local JSON, then cloud fallback.

        Raises ValueError if every attempt fails to produce valid JSON.
        """
        prompt = build_prompt(text)
        last_err: Exception | None = None
        for _ in range(self.max_retries):
            try:
                return parse_extraction(self._ollama(prompt))
            except Exception as exc:  # noqa: BLE001 - retry on any failure
                last_err = exc
        if self.cfg.extract_fallback:
            try:
                return parse_extraction(self._fallback(prompt))
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        raise ValueError(f"extraction failed after retries + fallback: {last_err}")

    def _fallback(self, prompt: str) -> str:
        """Cloud fallback for extraction only (EXTRACT_FALLBACK=provider:model)."""
        provider, _, model = self.cfg.extract_fallback.partition(":")
        if provider == "openai":
            return self._openai(model, prompt)
        if provider == "anthropic":
            return self._anthropic(model, prompt)
        raise ValueError(f"unknown EXTRACT_FALLBACK provider: {provider!r}")

    def _openai(self, model: str, prompt: str) -> str:
        if not self.cfg.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.openai_api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _anthropic(self, model: str, prompt: str) -> str:
        if not self.cfg.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.cfg.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
