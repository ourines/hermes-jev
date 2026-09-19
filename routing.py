"""Bounded model-candidate validation and Jev model-routing questions."""
from __future__ import annotations

import math
import re


MAX_CANDIDATES = 32
MAX_DESCRIPTION_CHARS = 2048
MAX_STRENGTHS = 12
_ROUTE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}\Z")


def _text(value, *, max_chars):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_chars and not any(
        ord(char) < 32 and char not in "\t" for char in value
    )


def validate_min_confidence(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("min_confidence must be a finite number between 0 and 1")
    return float(value)


def validate_candidates(raw):
    """Return a safe, stable candidate list; reject ambiguous or secret-like input."""
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_CANDIDATES:
        raise ValueError(f"candidates must contain 2..{MAX_CANDIDATES} model profiles")
    normalized = []
    seen_ids, seen_models = set(), set()
    for candidate in raw:
        if not isinstance(candidate, dict):
            raise ValueError("each model candidate must be an object")
        route_id = candidate.get("id")
        model = candidate.get("model")
        description = candidate.get("description")
        if not isinstance(route_id, str) or not _ROUTE_ID.fullmatch(route_id):
            raise ValueError("candidate id must be a short identifier")
        if not _text(model, max_chars=256) or any(char.isspace() for char in model):
            raise ValueError("candidate model must be a nonblank model identifier")
        if not _text(description, max_chars=MAX_DESCRIPTION_CHARS):
            raise ValueError("candidate description must be nonblank and bounded")
        if route_id in seen_ids or model in seen_models:
            raise ValueError("candidate ids and model identifiers must be unique")
        seen_ids.add(route_id)
        seen_models.add(model)
        item = {"id": route_id, "model": model, "description": description.strip()}
        for key in ("provider", "cost_tier", "speed_tier"):
            value = candidate.get(key)
            if value is not None:
                if not _text(value, max_chars=64):
                    raise ValueError(f"candidate {key} must be a short string")
                item[key] = value.strip()
        strengths = candidate.get("strengths")
        if strengths is not None:
            if not isinstance(strengths, list) or not 1 <= len(strengths) <= MAX_STRENGTHS:
                raise ValueError("candidate strengths must be a short list")
            if not all(_text(value, max_chars=128) for value in strengths):
                raise ValueError("candidate strengths must contain nonblank strings")
            item["strengths"] = [value.strip() for value in strengths]
        normalized.append(item)
    return normalized


def _candidate_criteria(candidates):
    criteria = {}
    for candidate in candidates:
        details = [candidate["description"]]
        if candidate.get("strengths"):
            details.append("Strengths: " + ", ".join(candidate["strengths"]))
        for key, label in (("cost_tier", "Cost"), ("speed_tier", "Speed"), ("provider", "Provider")):
            if candidate.get(key):
                details.append(f"{label}: {candidate[key]}")
        criteria[candidate["id"]] = " ".join(details)[:MAX_DESCRIPTION_CHARS]
    return criteria


def route_questions(candidates):
    """Build one finite choice question; the task remains the untrusted state."""
    return {
        "model": {
            "type": "choice",
            "instructions": (
                "Choose the single model profile that is the best fit for the user's task. "
                "Balance capability, task complexity, latency and cost. Do not choose a more "
                "expensive model unless the task needs its stated strengths. If the task is "
                "ambiguous, choose the safest capable profile rather than inventing requirements."
            ),
            "criteria": _candidate_criteria(candidates),
        }
    }


def route_result(result, candidates, min_confidence=None):
    """Compose a local route result; provider control fields never cross this boundary."""
    answer = result["answers"]["model"]
    selected_id = answer["choice"]
    selected = next(candidate for candidate in candidates if candidate["id"] == selected_id)
    confidence = answer.get("confidence")
    accepted = True
    needs_review = False
    if min_confidence is not None:
        accepted = isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and confidence >= min_confidence
        needs_review = not accepted
    decision = {
        "route_id": selected["id"],
        "model": selected["model"],
        "candidate": selected,
        "confidence": confidence,
        "probabilities": answer.get("probabilities"),
    }
    # Keep the same response boundary even when a test double or alternate evaluator returns
    # provider-shaped control fields. Only the client response fields are copied through.
    safe_result = {key: result[key] for key in ("model", "answers", "usage", "backend", "latency_ms") if key in result}
    return {
        **safe_result,
        "route": decision,
        "selected_model": selected["model"],
        "confidence": confidence,
        "probabilities": answer.get("probabilities"),
        "route_accepted": accepted,
        "route_needs_review": needs_review,
        "route_policy": {
            "min_confidence": min_confidence,
            "threshold_calibrated": False,
            "note": "A qualifying route may control the model field on the next Hermes provider request in this turn; it does not grant execution approval.",
        },
        "ok": True,
        "advisory_only": False,
        "execution_authorized": False,
    }