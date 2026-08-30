"""Provider-agnostic LLM client for enrichment.

Backends are pluggable and chosen by ``--provider`` / ``LLM_PROVIDER``:

* ``nvidia``  (default) - NVIDIA NIM's OpenAI-compatible ``/chat/completions`` over the
  ``requests`` dependency the project already has. Free hosted models
  (``meta/llama-3.3-70b-instruct`` by default). Key from ``NVIDIA_API_KEY``.
* ``anthropic`` - the Anthropic SDK, imported lazily so it is a genuinely optional
  dependency (same graceful-degrade pattern as ``src/recommend/semantic.py``). Key from
  ``ANTHROPIC_API_KEY``.
* ``stub`` - deterministic, offline, no network. The feature supplies a canned payload;
  used by tests and by ``build_features --provider stub`` to exercise the full
  schema -> persist -> flatten -> API pipeline without a key.

Cross-cutting behaviour lives here, not in the backends: a raw-response cache keyed by
``(book_id, family, prompt_version, provider, model)`` so re-runs are free; a ``--dry-run``
that renders the prompt and prints a token/cost estimate and writes nothing; and
retry-once-then-give-up on JSON that will not parse (the caller routes a give-up to the
review queue).

The API key is read only from the environment - never logged, cached, or written to disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import DATA_DIR, get_logger

logger = get_logger(__name__, log_filename="enrich.log")

DEFAULT_CACHE_DIR = DATA_DIR / "llm_cache"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

DEFAULT_MODELS = {
    "nvidia": "openai/gpt-oss-120b",
    "anthropic": "claude-sonnet-5",
    "stub": "stub",
}

# (input $/1M, output $/1M). NVIDIA's hosted build tier is free -> 0.0; still estimated
# in tokens so the dry-run report is meaningful. Anthropic rates from the claude-api skill.
# Unlisted models fall back to (0, 0) - fine for the free NVIDIA tier; pass an Anthropic
# model to get a real estimate.
PRICING: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.0, 0.0),
    "openai/gpt-oss-20b": (0.0, 0.0),
    "nvidia/nemotron-3-super-120b-a12b": (0.0, 0.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "stub": (0.0, 0.0),
}
_UNKNOWN_MODEL_PRICE = (0.0, 0.0)

_CHARS_PER_TOKEN = 4  # rough estimate for the dry-run report only
_EST_OUTPUT_TOKENS = 600


@dataclass(slots=True)
class LLMResult:
    """Outcome of one ``complete_json`` call."""

    model: str
    provider: str
    ok: bool = False
    data: dict | None = None
    raw_text: str = ""
    error: str | None = None
    from_cache: bool = False
    dry_run: bool = False
    rendered_prompt: str = ""
    token_estimate: int = 0
    cost_estimate: float = 0.0
    usage: dict = field(default_factory=dict)


def _price(model: str) -> tuple[float, float]:
    return PRICING.get(model, _UNKNOWN_MODEL_PRICE)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object out of a model response (handles code fences
    and leading/trailing prose). Raises ``ValueError`` if nothing parses.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("no JSON object found in response")


# --------------------------------------------------------------------------- #
# Backends                                                                     #
# --------------------------------------------------------------------------- #
class _NvidiaBackend:
    """NVIDIA NIM, OpenAI-compatible Chat Completions."""

    provider = "nvidia"

    def __init__(self, model: str, base_url: str, api_key: str | None,
                 max_tokens: int, temperature: float, timeout: float) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

    def available(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "NVIDIA_API_KEY is not set - export it before running a real pass"
        return True, ""

    def complete(self, system: str, user: str) -> tuple[str, dict]:
        import requests  # already a project dependency

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        resp = requests.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"NVIDIA API {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {}) or {}
        return text, {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }


class _AnthropicBackend:
    """Anthropic SDK, imported lazily so it stays an optional dependency."""

    provider = "anthropic"

    def __init__(self, model: str, api_key: str | None,
                 max_tokens: int, temperature: float, timeout: float) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._client = None

    def available(self) -> tuple[bool, str]:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "anthropic SDK not installed - run: pip install anthropic"
        if not (self._api_key or os.environ.get("ANTHROPIC_API_KEY")):
            return False, "ANTHROPIC_API_KEY is not set"
        return True, ""

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(timeout=self._timeout)
        return self._client

    def complete(self, system: str, user: str) -> tuple[str, dict]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        msg = self._get_client().messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system + "\n\nReturn only a single JSON object, no prose, no code fence.",
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        usage = getattr(msg, "usage", None)
        return text, {
            "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }


class _StubBackend:
    """No network. The payload is supplied by the caller (the feature's canned response)."""

    provider = "stub"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def complete(self, system: str, user: str) -> tuple[str, dict]:  # pragma: no cover
        raise RuntimeError("stub backend is driven via stub_payload, not complete()")


# --------------------------------------------------------------------------- #
# Client                                                                       #
# --------------------------------------------------------------------------- #
class LLMClient:
    def __init__(
        self,
        provider: str = "nvidia",
        model: str | None = None,
        *,
        dry_run: bool = False,
        cache_dir: Path | None = None,
        base_url: str | None = None,
        max_output_tokens: int = 2000,
        temperature: float = 0.2,
        timeout: float = 60.0,
    ) -> None:
        provider = (provider or "nvidia").lower()
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"unknown provider {provider!r}; choose from {sorted(DEFAULT_MODELS)}")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.dry_run = dry_run
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self._max_output_tokens = max_output_tokens

        if provider == "nvidia":
            self._backend: Any = _NvidiaBackend(
                self.model, base_url or os.environ.get("NVIDIA_BASE_URL", NVIDIA_BASE_URL),
                os.environ.get("NVIDIA_API_KEY"), max_output_tokens, temperature, timeout,
            )
        elif provider == "anthropic":
            self._backend = _AnthropicBackend(
                self.model, os.environ.get("ANTHROPIC_API_KEY"),
                max_output_tokens, temperature, timeout,
            )
        else:
            self._backend = _StubBackend()

        logger.info(
            "LLMClient ready: provider=%s model=%s dry_run=%s cache=%s",
            self.provider, self.model, self.dry_run, self.cache_dir,
        )

    # --- availability ---------------------------------------------------------- #
    def availability(self) -> tuple[bool, str]:
        if self.dry_run:
            return True, ""
        return self._backend.available()

    # --- cache -------------------------------------------------------------- #
    def _cache_path(self, book_id: int, family: str, feature: str, prompt_version: str) -> Path:
        # `feature` is part of the key because several features can share one `family`
        # (and thus one batching unit) while sending different prompts/schemas.
        key = hashlib.sha1(
            f"{book_id}|{family}|{feature}|{prompt_version}|{self.provider}|{self.model}".encode()
        ).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _cache_read(self, path: Path) -> tuple[str, dict] | None:
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
            return blob["raw_text"], blob.get("usage", {})
        except (json.JSONDecodeError, KeyError, OSError):
            logger.debug("ignoring unreadable cache file %s", path)
            return None

    def _cache_write(self, path: Path, raw_text: str, usage: dict) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "raw_text": raw_text,
                "usage": usage,
                "model": self.model,
                "provider": self.provider,
                "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }))
        except OSError:
            logger.warning("could not write raw-response cache to %s", path, exc_info=True)

    # --- cost -------------------------------------------------------------- #
    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        in_p, out_p = _price(self.model)
        return round(input_tokens / 1e6 * in_p + output_tokens / 1e6 * out_p, 6)

    # --- main entry point ------------------------------------------------- #
    def complete_json(
        self, *, system: str, user: str, book_id: int, family: str,
        prompt_version: str, feature: str = "", stub_payload: dict | None = None,
    ) -> LLMResult:
        rendered = f"===== SYSTEM =====\n{system}\n\n===== USER =====\n{user}"
        base = LLMResult(model=self.model, provider=self.provider, rendered_prompt=rendered)

        if self.dry_run:
            in_tok = _estimate_tokens(rendered)
            out_tok = min(self._max_output_tokens, _EST_OUTPUT_TOKENS)
            base.dry_run = True
            base.token_estimate = in_tok + out_tok
            base.cost_estimate = self._cost(in_tok, out_tok)
            logger.info(
                "DRY-RUN %s book_id=%s: ~%d in + ~%d out tokens, est $%.6f (model=%s)",
                family, book_id, in_tok, out_tok, base.cost_estimate, self.model,
            )
            print(f"\n--- DRY-RUN prompt: {family} / book_id={book_id} ---\n{rendered}\n"
                  f"--- est {in_tok + out_tok} tokens, ${base.cost_estimate:.6f} ---")
            return base

        if self.provider == "stub":
            payload = stub_payload if stub_payload is not None else {}
            base.ok = True
            base.data = payload
            base.raw_text = json.dumps(payload)
            logger.debug("stub %s book_id=%s -> canned payload", family, book_id)
            return base

        # cache hit?
        cache_path = self._cache_path(book_id, family, feature or family, prompt_version)
        cached = self._cache_read(cache_path)
        if cached is not None:
            raw_text, usage = cached
            base.from_cache = True
            base.raw_text = raw_text
            base.usage = usage
            try:
                base.data = _extract_json(raw_text)
                base.ok = True
            except ValueError as exc:
                base.error = f"cached response unparseable: {exc}"
            logger.debug("cache hit %s book_id=%s ok=%s", family, book_id, base.ok)
            return base

        # live call, with one retry on unparseable JSON
        last_err: str | None = None
        for attempt in (1, 2):
            try:
                raw_text, usage = self._backend.complete(system, user)
            except Exception as exc:  # noqa: BLE001 - surface as a result, not a crash
                last_err = f"backend error: {exc}"
                logger.warning("%s book_id=%s attempt %d: %s", family, book_id, attempt, last_err)
                break
            base.raw_text = raw_text
            base.usage = usage
            base.cost_estimate = self._cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            try:
                base.data = _extract_json(raw_text)
                base.ok = True
                self._cache_write(cache_path, raw_text, usage)
                logger.debug("live %s book_id=%s ok on attempt %d", family, book_id, attempt)
                return base
            except ValueError as exc:
                last_err = f"unparseable JSON (attempt {attempt}): {exc}"
                logger.warning("%s book_id=%s: %s", family, book_id, last_err)

        base.ok = False
        base.error = last_err or "unknown error"
        return base
