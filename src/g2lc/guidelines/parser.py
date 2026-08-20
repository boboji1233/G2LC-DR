"""Source-friendly guideline YAML parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from g2lc.errors import SourceValidationError
from g2lc.guidelines.ast import GuidelineBundle
from g2lc.utils.io import load_yaml, validation_error


def _expression(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or len(value) != 1:
        raise SourceValidationError(
            f"{context} must be a one-key DSL expression (all/any/not/eq/gte/lte/in/known)"
        )
    key, payload = next(iter(value.items()))
    if key in {"all", "any"}:
        if not isinstance(payload, list) or not payload:
            raise SourceValidationError(f"{context}.{key} must be a nonempty list")
        return {
            "op": "and" if key == "all" else "or",
            "terms": [
                _expression(term, f"{context}.{key}[{index}]") for index, term in enumerate(payload)
            ],
        }
    if key == "not":
        return {"op": "not", "term": _expression(payload, f"{context}.not")}
    if key in {"eq", "gte", "lte"}:
        if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], str):
            raise SourceValidationError(f"{context}.{key} must be [predicate, value]")
        operation = {"eq": "equals", "gte": "greater_equal", "lte": "less_equal"}[key]
        return {"op": operation, "predicate": payload[0], "value": payload[1]}
    if key == "in":
        if (
            not isinstance(payload, list)
            or len(payload) != 2
            or not isinstance(payload[0], str)
            or not isinstance(payload[1], list)
        ):
            raise SourceValidationError(f"{context}.in must be [predicate, [values...]]")
        return {"op": "in_set", "predicate": payload[0], "values": payload[1]}
    if key == "known":
        if not isinstance(payload, str):
            raise SourceValidationError(f"{context}.known must name one predicate")
        return {"op": "known", "predicate": payload}
    raise SourceValidationError(f"{context} uses unsupported DSL operator {key!r}")


def _normalize(raw: Any) -> Any:
    if not isinstance(raw, dict) or not isinstance(raw.get("guidelines"), list):
        raise SourceValidationError("top-level 'guidelines' must be a nonempty list")
    normalized = dict(raw)
    guidelines: list[Any] = []
    for guideline_index, guideline in enumerate(raw["guidelines"]):
        if not isinstance(guideline, dict) or not isinstance(guideline.get("rules"), list):
            raise SourceValidationError(
                f"guidelines[{guideline_index}].rules must be a nonempty list"
            )
        normalized_guideline = dict(guideline)
        rules: list[Any] = []
        for rule_index, rule in enumerate(guideline["rules"]):
            if not isinstance(rule, dict) or "when" not in rule or "then" not in rule:
                raise SourceValidationError(
                    f"guidelines[{guideline_index}].rules[{rule_index}] requires when and then"
                )
            normalized_rule = dict(rule)
            normalized_rule["when"] = _expression(
                rule["when"], f"guidelines[{guideline_index}].rules[{rule_index}].when"
            )
            normalized_rule["action"] = {"values": normalized_rule.pop("then")}
            rules.append(normalized_rule)
        normalized_guideline["rules"] = rules
        if "default_action" in normalized_guideline:
            normalized_guideline["default_action"] = {
                "values": normalized_guideline["default_action"]
            }
        guidelines.append(normalized_guideline)
    normalized["guidelines"] = guidelines
    return normalized


def load_guidelines(path: str | Path) -> GuidelineBundle:
    """Load the concise DSL into a strictly typed bundle."""

    try:
        return GuidelineBundle.model_validate(_normalize(load_yaml(path)))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc
