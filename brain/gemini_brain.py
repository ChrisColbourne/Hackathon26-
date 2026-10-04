"""Gemini: a JPEG of the board -> BoardAnalysis (Contract 2).

Uses the Interactions API with structured JSON output. Flash answers first;
if it's unsure (confidence < PRO_FALLBACK_BELOW) or the reply doesn't parse,
Pro is asked and the more confident answer wins.

If Gemini rejects our JSON schema (field support varies by model), we retry
once with plain JSON mode and the schema pasted into the prompt, and remember
that choice for the rest of the session.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime
from pathlib import Path

from google import genai
from pydantic import ValidationError

from . import config
from .demo_cache import DemoCache
from .prompts import SYSTEM, user_turn
from .schemas import BoardAnalysis
from .threads import run_in_daemon

TRANSIENT_PENALTY_S = 90      # 503 / timeout: try the others first for a while
RATE_LIMIT_PENALTY_S = 600    # daily quota: don't bother it for a good while

log = logging.getLogger("gemini")

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def _strip_fences(s: str) -> str:
    return _FENCE.sub("", s.strip()).strip()


class GeminiBrain:
    def __init__(
        self,
        client: genai.Client | None = None,
        flash: str = config.FLASH_MODEL,
        pro: str = config.PRO_MODEL,
        fallback_below: float = config.PRO_FALLBACK_BELOW,
        record_dir: Path | None = config.RECORD_DIR,
    ):
        # One client per API key, built lazily; a 429 rotates to the next key.
        self._keys: list[str | None] = list(config.GEMINI_API_KEYS) or [None]
        self._key_idx = 0
        self._clients: dict[int, genai.Client] = {}
        if client is not None:
            self._clients[0] = client
        # Calls run on daemon threads so WE hold the deadline (the SDK's own
        # timeout has let requests sit for minutes) and an in-flight call can
        # never block process exit.
        self._penalty_until: dict[str, float] = {}   # model -> demoted until (monotonic seconds)
        self.flash, self.pro, self.fallback_below = flash, pro, fallback_below
        # Asked in order until one answers with confidence >= fallback_below.
        self.chain: list[tuple[str, str]] = [(flash, config.FLASH_THINKING)]
        if pro:
            self.chain.append((pro, config.PRO_THINKING))
        self.chain += [(m, config.FLASH_THINKING) for m in config.ALT_MODELS if m not in (flash, pro)]
        self.record_dir = record_dir
        self.cache = DemoCache()
        self.prefer_cache = config.PREFER_CACHE
        self.schema_mode = True          # flips to False if the API rejects our schema
        self.last_raw: str | None = None
        self.last_model: str | None = None
        self.calls = 0

    # ---- public --------------------------------------------------------
    def see(self, jpeg: bytes, context: dict | None = None) -> BoardAnalysis:
        """One check of the board. Raises only if both models AND the cache fail."""
        if self.prefer_cache and (hit := self.cache.lookup(jpeg)) is not None:
            self.last_model = "cache"
            return hit

        text = user_turn(context)
        stamp = self._record_image(jpeg)       # saved first, so a failed check still leaves evidence
        best: BoardAnalysis | None = None
        for attempt in range(2):
            overloaded = False
            for model, thinking in self._ordered_chain():
                if best is not None and not self._should_escalate(best):
                    break
                if best is not None:
                    log.info("confidence %.2f < %.2f on visible math; asking %s",
                             best.confidence, self.fallback_below, model)
                try:
                    a = self._ask(model, jpeg, text, thinking)
                except Exception as e:
                    log.warning("%s failed: %s", model, str(e)[:200])
                    self._penalize(model, e)
                    overloaded |= _is_overloaded(e)
                    continue
                if best is None or a.confidence >= best.confidence:
                    best = a
            if best is not None or not overloaded or attempt:
                break
            # Every model said "high demand" at once (seen Oct 3). Those spikes
            # clear within seconds, so one more pass is worth 2 s of otter time.
            log.info("all models overloaded; one retry in 2 s")
            time.sleep(2)

        if best is None:
            if (hit := self.cache.lookup(jpeg)) is not None:
                log.warning("all models failed; serving demo cache")
                self.last_model = "cache"
                return hit
            raise RuntimeError("all Gemini models failed and no cached reply matches")

        self._record_json(stamp, best)
        return best

    def _should_escalate(self, a: BoardAnalysis) -> bool:
        """Re-ask only when there IS math on the board and the model is unsure
        about it. "Blank board, confidence 0" is a complete answer; asking the
        next model would only burn quota."""
        saw_math = bool(a.problem.strip() or a.steps)
        return saw_math and a.confidence < self.fallback_below

    def _ordered_chain(self) -> list[tuple[str, str]]:
        """The chain with recently-failed models moved to the back. On a bad
        evening (Oct 3: 503s and 35 s timeouts on 3.8/3.7 while 3.6 answered in
        3 s) this turns a 70 s check into a 5 s one."""
        now = time.monotonic()
        healthy = [mt for mt in self.chain if self._penalty_until.get(mt[0], 0.0) <= now]
        demoted = [mt for mt in self.chain if self._penalty_until.get(mt[0], 0.0) > now]
        return healthy + demoted

    def _penalize(self, model: str, e: Exception) -> None:
        secs = RATE_LIMIT_PENALTY_S if _is_rate_limit(e) else TRANSIENT_PENALTY_S if _is_transient(e) else 0
        if secs:
            self._penalty_until[model] = time.monotonic() + secs
            log.info("%s demoted for %ds", model, secs)

    # ---- internals -----------------------------------------------------
    @property
    def client(self) -> genai.Client:
        i = self._key_idx
        if i not in self._clients:
            kwargs: dict = {"http_options": {
                "timeout": int(config.GEMINI_TIMEOUT_S * 1000),   # milliseconds here
                # attempts=0 is the only value that means "never retry": with 1 the
                # SDK still retries once, sleeping for the 429's whole Retry-After
                # (4710 s on a free-tier daily limit!). The status-code override
                # names a code that never occurs, so no response is "retryable".
                "retry_options": {"attempts": 0, "http_status_codes": [599]},
            }}
            if self._keys[i]:
                kwargs["api_key"] = self._keys[i]
            self._clients[i] = genai.Client(**kwargs)
        return self._clients[i]

    def _rotate_key(self) -> None:
        self._key_idx = (self._key_idx + 1) % len(self._keys)

    def _guarded_call(self, model: str, jpeg: bytes, text: str, thinking: str, with_schema: bool) -> str:
        """_call with a hard deadline and API-key rotation on rate limits."""
        deadline = config.GEMINI_TIMEOUT_S + 5
        for _ in range(len(self._keys)):
            fut = run_in_daemon(self._call, model, jpeg, text, thinking, with_schema, name="gemini")
            try:
                return fut.result(timeout=deadline)
            except FuturesTimeout:
                raise TimeoutError(f"{model}: no reply within {deadline:.0f}s") from None
            except Exception as e:
                if _is_rate_limit(e) and len(self._keys) > 1:
                    log.warning("%s rate-limited on key #%d; rotating", model, self._key_idx + 1)
                    self._rotate_key()
                    continue
                raise
        raise RuntimeError(f"{model}: rate-limited on all {len(self._keys)} API keys")

    def _ask(self, model: str, jpeg: bytes, text: str, thinking: str) -> BoardAnalysis:
        t0 = time.monotonic()
        try:
            raw = self._guarded_call(model, jpeg, text, thinking, with_schema=self.schema_mode)
        except Exception as e:
            if self.schema_mode and _looks_like_schema_error(e):
                log.warning("schema rejected by %s (%s); switching to plain JSON mode", model, e)
                self.schema_mode = False
                raw = self._guarded_call(model, jpeg, text, thinking, with_schema=False)
            else:
                raise
        self.calls += 1
        self.last_raw, self.last_model = raw, model
        try:
            analysis = BoardAnalysis.model_validate_json(_strip_fences(raw))
        except ValidationError as e:
            log.warning("%s returned JSON that doesn't fit the schema: %s", model, str(e)[:300])
            raise
        log.info("%s %.1fs conf=%.2f topic=%s first_error=%s", model, time.monotonic() - t0,
                 analysis.confidence, analysis.topic, analysis.first_error_line)
        return analysis

    def _call(self, model: str, jpeg: bytes, text: str, thinking: str, with_schema: bool) -> str:
        prompt = text
        response_format: dict = {"type": "text", "mime_type": "application/json"}
        if with_schema:
            response_format["schema"] = BoardAnalysis.model_json_schema()
        else:
            prompt += "\n\nReturn ONLY a JSON object with exactly this schema:\n" + json.dumps(
                BoardAnalysis.model_json_schema())

        interaction = self.client.interactions.create(
            model=model,
            system_instruction=SYSTEM,
            input=[
                {"type": "text", "text": prompt},
                {"type": "image", "data": base64.b64encode(jpeg).decode(), "mime_type": "image/jpeg"},
            ],
            response_format=response_format,
            generation_config={"thinking_level": thinking, "temperature": config.TEMPERATURE},
            timeout=config.GEMINI_TIMEOUT_S,                        # seconds here
        )
        out = getattr(interaction, "output_text", None)
        if not out:
            raise RuntimeError(f"{model}: empty output_text")
        return out

    def _record_image(self, jpeg: bytes) -> str | None:
        if not self.record_dir:
            return None
        try:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%H%M%S_%f")[:-3]
            (self.record_dir / f"{stamp}.jpg").write_bytes(jpeg)
            return stamp
        except OSError as e:
            log.debug("record failed: %s", e)
            return None

    def _record_json(self, stamp: str | None, analysis: BoardAnalysis) -> None:
        if not stamp or not self.record_dir:
            return
        try:
            (self.record_dir / f"{stamp}.json").write_text(analysis.model_dump_json(indent=2))
        except OSError as e:
            log.debug("record failed: %s", e)


def _is_overloaded(e: Exception) -> bool:
    s = str(e)
    return "503" in s or "high demand" in s or "overloaded" in s.lower() or "UNAVAILABLE" in s


def _is_transient(e: Exception) -> bool:
    return _is_overloaded(e) or isinstance(e, TimeoutError) or "timed out" in str(e).lower()


def _is_rate_limit(e: Exception) -> bool:
    s = str(e)
    return ("429" in s or "RESOURCE_EXHAUSTED" in s or "Too Many Requests" in s or "rate-limited" in s
            or "RateLimit" in type(e).__name__)


def _looks_like_schema_error(e: Exception) -> bool:
    s = str(e).lower()
    # Only treat it as a schema problem when the message says so; a 503 or a
    # rejected thinking level must not silently switch us to plain-JSON mode.
    return "schema" in s or "response_format" in s
