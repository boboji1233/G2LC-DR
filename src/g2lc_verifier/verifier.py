"""Independent raw-source verifier for action-only Stage-1.5 certificates."""

from __future__ import annotations

import hashlib
import itertools
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
import z3
from pydantic import BaseModel, ConfigDict

from g2lc.errors import CertificateVerificationError


class VerificationReport(BaseModel):
    """Machine-readable independent verification outcome."""

    model_config = ConfigDict(extra="forbid")
    valid: bool
    certificate_type: str
    checks: list[str]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _typed_key(value: Any) -> str:
    if value is None:
        return "null:"
    if type(value) is bool:
        return f"bool:{str(value).lower()}"
    if type(value) is str:
        return f"str:{value}"
    if type(value) is int:
        return f"int:{value}"
    if type(value) is float:
        return f"float:{value!r}"
    raise CertificateVerificationError(f"non-scalar semantic value {value!r}")


def _equal(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _contains(values: list[Any], candidate: Any) -> bool:
    return any(_equal(item, candidate) for item in values)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CertificateVerificationError(f"source is not a mapping: {path}")
    return value


def _root_for(certificate_path: Path, project_config: str) -> tuple[Path, Path]:
    project = Path(project_config)
    if project.is_absolute() and project.is_file():
        return project.parent, project
    for candidate in (certificate_path.parent, *certificate_path.parents, Path.cwd().resolve()):
        resolved = candidate / project
        if resolved.is_file():
            return candidate, resolved
    raise CertificateVerificationError(f"cannot resolve recorded project_config {project_config!r}")


def _condition(raw: dict[str, Any], state: dict[str, Any]) -> bool:
    return _equal(state[raw["predicate"]], raw["equals"])


def _feasible(ontology: dict[str, Any], state: dict[str, Any]) -> bool:
    program = ontology.get("feasibility", {"schema_version": "1.0", "constraints": []})
    for constraint in program.get("constraints", []):
        kind = constraint["kind"]
        if kind == "implication":
            if _condition(constraint["if"], state) and not _condition(constraint["then"], state):
                return False
        elif kind in {"mutual_exclusion", "at_most_one"}:
            if sum(_condition(item, state) for item in constraint["conditions"]) > 1:
                return False
        elif kind == "exactly_one":
            if sum(_condition(item, state) for item in constraint["conditions"]) != 1:
                return False
        elif kind == "conditional_allowed":
            if _condition(constraint["if"], state) and not _contains(
                constraint["allowed_values"], state[constraint["predicate"]]
            ):
                return False
        elif kind == "derived_equality":
            source = state[constraint["source_predicate"]]
            expected = constraint.get("value_mapping", {}).get(_typed_key(source), source)
            if not _equal(expected, state[constraint["target_predicate"]]):
                return False
        elif kind == "parent_child":
            parent = state[constraint["parent_predicate"]]
            if _contains(constraint["when_parent_values"], parent) and not _contains(
                constraint["allowed_child_values"], state[constraint["child_predicate"]]
            ):
                return False
        else:
            raise CertificateVerificationError(f"unsupported feasibility kind {kind!r}")
    return True


def _derivations_consistent(graph: dict[str, Any], state: dict[str, Any]) -> bool:
    for rule in graph.get("rules", []):
        if len(rule["input_predicates"]) != 1 or len(rule["output_predicates"]) != 1:
            return False
        source = state[rule["input_predicates"][0]]
        expected = rule.get("value_mapping", {}).get(_typed_key(source))
        if expected is None or not _equal(expected, state[rule["output_predicates"][0]]):
            return False
    return True


def _states(
    ontology: dict[str, Any], graph: dict[str, Any], max_states: int
) -> list[dict[str, Any]]:
    predicates = sorted(ontology["predicates"], key=lambda item: item["id"])
    count = 1
    for predicate in predicates:
        count *= len(predicate["allowed_values"])
    if count > max_states:
        raise CertificateVerificationError(
            f"independent finite verification exceeds max_states={max_states}"
        )
    result = []
    for values in itertools.product(*(item["allowed_values"] for item in predicates)):
        state = {item["id"]: value for item, value in zip(predicates, values, strict=True)}
        if _feasible(ontology, state) and _derivations_consistent(graph, state):
            result.append(state)
    return result


def _expression(raw: dict[str, Any], state: dict[str, Any]) -> bool:
    key, payload = next(iter(raw.items()))
    if key == "all":
        return all(_expression(item, state) for item in payload)
    if key == "any":
        return any(_expression(item, state) for item in payload)
    if key == "not":
        return not _expression(payload, state)
    if key == "eq":
        return _equal(state[payload[0]], payload[1])
    if key == "in":
        return _contains(payload[1], state[payload[0]])
    if key == "gte":
        return bool(state[payload[0]] >= payload[1])
    if key == "lte":
        return bool(state[payload[0]] <= payload[1])
    if key == "known":
        return state[payload] is not None
    raise CertificateVerificationError(f"unsupported guideline operator {key!r}")


def _decision(guideline: dict[str, Any], state: dict[str, Any]) -> str:
    triggered = [rule for rule in guideline["rules"] if _expression(rule["when"], state)]
    if triggered:
        priority = max(rule["priority"] for rule in triggered)
        actions = {
            _canonical({"values": rule["then"]}): {"values": rule["then"]}
            for rule in triggered
            if rule["priority"] == priority
        }
        normalized = [actions[key] for key in sorted(actions)]
    else:
        default = guideline.get("default_action")
        normalized = [{"values": default}] if default is not None else []
    return _canonical(normalized)


def _expression_predicates(raw: dict[str, Any]) -> set[str]:
    key, payload = next(iter(raw.items()))
    if key in {"all", "any"}:
        return set().union(*(_expression_predicates(item) for item in payload))
    if key == "not":
        return _expression_predicates(payload)
    return {payload if key == "known" else payload[0]}


def _reference_clauses(guidelines: list[dict[str, Any]]) -> dict[str, list[str]]:
    clauses: dict[str, list[str]] = {}
    for guideline in guidelines:
        for rule in guideline["rules"]:
            for predicate in _expression_predicates(rule["when"]):
                clauses.setdefault(predicate, []).append(f"{guideline['id']}:{rule['id']}")
    return {predicate: sorted(items) for predicate, items in clauses.items()}


def _expected_oos(
    ontology: dict[str, Any],
    guidelines: list[dict[str, Any]],
    target_modalities: set[str],
) -> list[dict[str, Any]]:
    domains = {item["id"]: item for item in ontology["predicates"]}
    clauses = _reference_clauses(guidelines)
    findings: list[dict[str, Any]] = []
    for predicate_id in sorted(clauses):
        predicate = domains.get(predicate_id)
        if predicate is None:
            reason = "predicate is not declared in the evidence ontology"
            modalities: list[str] = []
        else:
            modalities = sorted(predicate["modalities"])
            if predicate.get("observability") == "EXTERNAL_CLINICAL":
                reason = "predicate is external clinical evidence, not image-observable"
            elif not target_modalities.intersection(modalities):
                reason = "predicate is not observable in the project target modality"
            else:
                continue
        findings.append(
            {
                "predicate_id": predicate_id,
                "reason": reason,
                "required_modalities": modalities,
                "source_clauses": clauses[predicate_id],
            }
        )
    return findings


def _applicable(operator: dict[str, Any], state: dict[str, Any]) -> bool:
    return all(
        _contains(item["allowed_values"], state[item["predicate_id"]])
        for item in operator.get("required_evidence_conditions", [])
    )


def _derived_values(
    selected: list[dict[str, Any]], graph: dict[str, Any], state: dict[str, Any]
) -> tuple[dict[str, Any], set[str]]:
    values: dict[str, Any] = {}
    direct: set[str] = set()
    for operator in selected:
        if not _applicable(operator, state):
            continue
        for predicate in operator.get("output_predicates", []):
            if predicate not in operator.get("value_mappings", {}):
                values[predicate] = state[predicate]
                direct.add(predicate)
    changed = True
    while changed:
        changed = False
        for rule in sorted(graph.get("rules", []), key=lambda item: item["id"]):
            source = rule["input_predicates"][0]
            target = rule["output_predicates"][0]
            if source in values and target not in values:
                values[target] = rule["value_mapping"][_typed_key(values[source])]
                changed = True
    return values, direct


def _derived_predicates(selected: list[dict[str, Any]], graph: dict[str, Any]) -> list[str]:
    exact = {
        predicate
        for operator in selected
        for predicate in operator.get("output_predicates", [])
        if predicate not in operator.get("value_mappings", {})
    }
    changed = True
    while changed:
        changed = False
        for rule in graph.get("rules", []):
            if rule["input_predicates"][0] in exact:
                before = len(exact)
                exact.add(rule["output_predicates"][0])
                changed = changed or len(exact) != before
    return sorted(exact)


def _observation(
    selected: list[dict[str, Any]], graph: dict[str, Any], state: dict[str, Any]
) -> str:
    result: list[list[Any]] = []
    for operator in sorted(selected, key=lambda item: item["id"]):
        applicable = _applicable(operator, state)
        result.append([operator["id"], "$applicable", applicable])
        if not applicable:
            continue
        for predicate in sorted(operator.get("output_predicates", [])):
            value = state[predicate]
            mapping = operator.get("value_mappings", {}).get(predicate)
            observed = mapping[_typed_key(value)] if mapping is not None else value
            result.append([operator["id"], predicate, observed])
    derived, direct = _derived_values(selected, graph, state)
    for predicate in sorted(set(derived) - direct):
        result.append(["$derived", predicate, derived[predicate]])
    return _canonical(result)


def _operator_closure(ids: set[str], operator_map: dict[str, dict[str, Any]]) -> set[str]:
    closure = set(ids)
    pending = [
        required
        for item in ids
        for required in operator_map[item].get("required_operator_ids", [])
        if item in operator_map
    ]
    while pending:
        item = pending.pop()
        if item in closure or item not in operator_map:
            continue
        closure.add(item)
        pending.extend(operator_map[item].get("required_operator_ids", []))
    return closure


def _available(
    project: dict[str, Any], operators: dict[str, Any], *, include_repair: bool
) -> list[str]:
    target = set(project["target_modalities"])
    forbidden = set(project.get("forbidden_operators", []))
    candidates = {
        item["id"]: item
        for item in operators["operators"]
        if item["id"] not in forbidden
        and target.intersection(item["modalities"])
        and set(item.get("required_modalities", [])).issubset(target)
        and (include_repair or item.get("availability", "AVAILABLE") == "AVAILABLE")
    }
    changed = True
    while changed:
        changed = False
        for item, operator in list(candidates.items()):
            if not set(operator.get("required_operator_ids", [])).issubset(candidates):
                del candidates[item]
                changed = True
    return sorted(candidates)


def _scheme_valid(ids: set[str], operator_map: dict[str, dict[str, Any]]) -> bool:
    return all(
        set(operator_map[item].get("required_operator_ids", [])).issubset(ids) for item in ids
    )


def _scheme_cost(
    ids: set[str], operator_map: dict[str, dict[str, Any]], weight: Decimal
) -> Decimal:
    return sum(
        (
            Decimal(str(operator_map[item]["cost"]))
            + weight * Decimal(str(operator_map[item].get("instability", 0)))
            for item in ids
        ),
        start=Decimal(0),
    )


def _rows(
    states: list[dict[str, Any]],
    guidelines: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    graph: dict[str, Any],
) -> tuple[bool, int]:
    observations = [_observation(selected, graph, state) for state in states]
    decisions = [tuple(_decision(guideline, state) for guideline in guidelines) for state in states]
    distinctions = 0
    executable = True
    for left in range(len(states)):
        for right in range(left + 1, len(states)):
            if decisions[left] != decisions[right]:
                distinctions += 1
                if observations[left] == observations[right]:
                    executable = False
    return executable, distinctions


def _uncovered_counterexamples(
    states: list[dict[str, Any]],
    guidelines: list[dict[str, Any]],
    available: list[dict[str, Any]],
    graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    observations = [_observation(available, graph, state) for state in states]
    action_rows = [
        {guideline["id"]: _decision(guideline, state) for guideline in guidelines}
        for state in states
    ]
    referenced = set().union(
        *(
            _expression_predicates(rule["when"])
            for guideline in guidelines
            for rule in guideline["rules"]
        )
    )
    counterexamples: list[dict[str, Any]] = []
    missing: set[str] = set()
    for left in range(len(states)):
        for right in range(left + 1, len(states)):
            differing = sorted(
                guideline["id"]
                for guideline in guidelines
                if action_rows[left][guideline["id"]] != action_rows[right][guideline["id"]]
            )
            if not differing or observations[left] != observations[right]:
                continue
            missing.update(
                predicate
                for predicate in referenced
                if not _equal(states[left][predicate], states[right][predicate])
            )
            counterexamples.append(
                {
                    "left": {"values": states[left]},
                    "right": {"values": states[right]},
                    "differing_guidelines": differing,
                    "left_actions": {item: action_rows[left][item] for item in differing},
                    "right_actions": {item: action_rows[right][item] for item in differing},
                }
            )
    return counterexamples, sorted(missing)


def _optimum(
    candidates: list[str],
    required: set[str],
    operator_map: dict[str, dict[str, Any]],
    weight: Decimal,
    states: list[dict[str, Any]],
    guidelines: list[dict[str, Any]],
    graph: dict[str, Any],
) -> tuple[Decimal, int, list[str]] | None:
    if len(candidates) > 24:
        raise CertificateVerificationError("independent optimum is limited to 24 operators")
    best: tuple[Decimal, int, tuple[str, ...]] | None = None
    for flags in itertools.product((False, True), repeat=len(candidates)):
        ids = {item for item, selected in zip(candidates, flags, strict=True) if selected}
        if not required.issubset(ids) or not _scheme_valid(ids, operator_map):
            continue
        selected = [operator_map[item] for item in sorted(ids)]
        if not _rows(states, guidelines, selected, graph)[0]:
            continue
        key = (_scheme_cost(ids, operator_map, weight), len(ids), tuple(sorted(ids)))
        if best is None or key < best:
            best = key
    if best is None:
        return None
    return best[0], best[1], list(best[2])


def _normalized_expression(raw: dict[str, Any]) -> dict[str, Any]:
    key, payload = next(iter(raw.items()))
    if key in {"all", "any"}:
        return {
            "op": "and" if key == "all" else "or",
            "terms": [_normalized_expression(item) for item in payload],
        }
    if key == "not":
        return {"op": "not", "term": _normalized_expression(payload)}
    if key in {"eq", "gte", "lte"}:
        return {
            "op": {"eq": "equals", "gte": "greater_equal", "lte": "less_equal"}[key],
            "predicate": payload[0],
            "value": payload[1],
        }
    if key == "in":
        return {"op": "in_set", "predicate": payload[0], "values": payload[1]}
    if key == "known":
        return {"op": "known", "predicate": payload}
    raise CertificateVerificationError(f"unsupported guideline operator {key!r}")


def _decision_program(guidelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": guideline["id"],
            "version": guideline["version"],
            "action_schema": guideline["action_schema"],
            "rules": [
                {
                    "id": rule["id"],
                    "priority": rule["priority"],
                    "when": _normalized_expression(rule["when"]),
                    "action": {"values": rule["then"]},
                }
                for rule in guideline["rules"]
            ],
            "default_action": (
                {"values": guideline["default_action"]}
                if guideline.get("default_action") is not None
                else None
            ),
        }
        for guideline in sorted(guidelines, key=lambda item: (item["id"], item["version"]))
    ]


def _z3_domains(ontology: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        item["id"]: {_typed_key(value): index for index, value in enumerate(item["allowed_values"])}
        for item in ontology["predicates"]
    }


def _z3_value(
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
    predicate: str,
    value: Any,
) -> z3.BoolRef:
    return variables[predicate] == domains[predicate][_typed_key(value)]


def _z3_expression(
    raw: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
    ontology: dict[str, Any],
) -> z3.BoolRef:
    key, payload = next(iter(raw.items()))
    if key == "all":
        return z3.And(*(_z3_expression(item, variables, domains, ontology) for item in payload))
    if key == "any":
        return z3.Or(*(_z3_expression(item, variables, domains, ontology) for item in payload))
    if key == "not":
        return z3.Not(_z3_expression(payload, variables, domains, ontology))
    if key == "eq":
        return _z3_value(variables, domains, payload[0], payload[1])
    if key == "in":
        return z3.Or(*(_z3_value(variables, domains, payload[0], item) for item in payload[1]))
    if key in {"gte", "lte"}:
        predicate_map = {item["id"]: item for item in ontology["predicates"]}
        allowed = predicate_map[payload[0]]["allowed_values"]
        matching = [
            value
            for value in allowed
            if (value >= payload[1] if key == "gte" else value <= payload[1])
        ]
        return z3.Or(*(_z3_value(variables, domains, payload[0], item) for item in matching))
    if key == "known":
        return z3.BoolVal(True)
    raise CertificateVerificationError(f"unsupported guideline operator {key!r}")


def _z3_feasibility(
    ontology: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    result: list[z3.BoolRef] = []
    for constraint in ontology.get("feasibility", {}).get("constraints", []):
        kind = constraint["kind"]
        if kind == "implication":
            result.append(
                z3.Implies(
                    _z3_value(
                        variables,
                        domains,
                        constraint["if"]["predicate"],
                        constraint["if"]["equals"],
                    ),
                    _z3_value(
                        variables,
                        domains,
                        constraint["then"]["predicate"],
                        constraint["then"]["equals"],
                    ),
                )
            )
        elif kind in {"mutual_exclusion", "at_most_one", "exactly_one"}:
            terms = [
                z3.If(_z3_value(variables, domains, item["predicate"], item["equals"]), 1, 0)
                for item in constraint["conditions"]
            ]
            result.append(sum(terms) == 1 if kind == "exactly_one" else sum(terms) <= 1)
        elif kind == "conditional_allowed":
            result.append(
                z3.Implies(
                    _z3_value(
                        variables,
                        domains,
                        constraint["if"]["predicate"],
                        constraint["if"]["equals"],
                    ),
                    z3.Or(
                        *(
                            _z3_value(variables, domains, constraint["predicate"], value)
                            for value in constraint["allowed_values"]
                        )
                    ),
                )
            )
        elif kind == "derived_equality":
            mapping = constraint.get("value_mapping", {})
            source_domain = domains[constraint["source_predicate"]]
            for key, index in source_domain.items():
                source_value = next(
                    value
                    for value in next(
                        item
                        for item in ontology["predicates"]
                        if item["id"] == constraint["source_predicate"]
                    )["allowed_values"]
                    if _typed_key(value) == key
                )
                result.append(
                    z3.Implies(
                        variables[constraint["source_predicate"]] == index,
                        _z3_value(
                            variables,
                            domains,
                            constraint["target_predicate"],
                            mapping.get(key, source_value),
                        ),
                    )
                )
        elif kind == "parent_child":
            result.append(
                z3.Implies(
                    z3.Or(
                        *(
                            _z3_value(variables, domains, constraint["parent_predicate"], value)
                            for value in constraint["when_parent_values"]
                        )
                    ),
                    z3.Or(
                        *(
                            _z3_value(variables, domains, constraint["child_predicate"], value)
                            for value in constraint["allowed_child_values"]
                        )
                    ),
                )
            )
        else:
            raise CertificateVerificationError(f"unsupported feasibility kind {kind!r}")
    return result


def _z3_derivations(
    graph: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    result: list[z3.BoolRef] = []
    for rule in graph.get("rules", []):
        source = rule["input_predicates"][0]
        target = rule["output_predicates"][0]
        for key, index in domains[source].items():
            result.append(
                z3.Implies(
                    variables[source] == index,
                    _z3_value(variables, domains, target, rule["value_mapping"][key]),
                )
            )
    return result


def _z3_decision(
    guideline: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
    ontology: dict[str, Any],
) -> z3.ArithRef:
    empty = _canonical([])
    action_keys = {_canonical([{"values": rule["then"]}]) for rule in guideline["rules"]}
    if guideline.get("default_action") is not None:
        action_keys.add(_canonical([{"values": guideline["default_action"]}]))
    action_keys.add(empty)
    codes = {key: index for index, key in enumerate(sorted(action_keys))}
    default_key = (
        _canonical([{"values": guideline["default_action"]}])
        if guideline.get("default_action") is not None
        else empty
    )
    decision: z3.ArithRef = z3.IntVal(codes[default_key])
    priorities = sorted({rule["priority"] for rule in guideline["rules"]})
    for priority in priorities:
        rules = [item for item in guideline["rules"] if item["priority"] == priority]
        condition = z3.Or(
            *(_z3_expression(item["when"], variables, domains, ontology) for item in rules)
        )
        action_key = _canonical([{"values": rules[0]["then"]}])
        decision = z3.If(condition, codes[action_key], decision)
    return decision


def _z3_applicable(
    operator: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
) -> z3.BoolRef:
    return z3.And(
        *(
            z3.Or(
                *(
                    _z3_value(variables, domains, item["predicate_id"], value)
                    for value in item["allowed_values"]
                )
            )
            for item in operator.get("required_evidence_conditions", [])
        )
    )


def _z3_mapped_output(
    predicate: str,
    mapping: dict[str, Any],
    variables: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
) -> z3.ArithRef:
    outputs = sorted({_typed_key(value) for value in mapping.values()})
    output_codes = {key: index for index, key in enumerate(outputs)}
    expression: z3.ArithRef = z3.IntVal(0)
    for key, index in domains[predicate].items():
        expression = z3.If(
            variables[predicate] == index,
            output_codes[_typed_key(mapping[key])],
            expression,
        )
    return expression


def _z3_observation_equal(
    selected: list[dict[str, Any]],
    left: dict[str, z3.ArithRef],
    right: dict[str, z3.ArithRef],
    domains: dict[str, dict[str, int]],
) -> list[z3.BoolRef]:
    result: list[z3.BoolRef] = []
    for operator in selected:
        left_applicable = _z3_applicable(operator, left, domains)
        right_applicable = _z3_applicable(operator, right, domains)
        result.append(left_applicable == right_applicable)
        for predicate in operator.get("output_predicates", []):
            mapping = operator.get("value_mappings", {}).get(predicate)
            equality = (
                left[predicate] == right[predicate]
                if mapping is None
                else _z3_mapped_output(predicate, mapping, left, domains)
                == _z3_mapped_output(predicate, mapping, right, domains)
            )
            result.append(z3.Implies(left_applicable, equality))
    return result


def _symbolic_counterexample(
    ontology: dict[str, Any],
    guidelines: list[dict[str, Any]],
    operators: list[dict[str, Any]],
    graph: dict[str, Any],
) -> dict[str, Any] | None:
    domains = _z3_domains(ontology)
    predicate_map = {item["id"]: item for item in ontology["predicates"]}
    left = {item: z3.Int(f"left__{item}") for item in sorted(domains)}
    right = {item: z3.Int(f"right__{item}") for item in sorted(domains)}
    solver = z3.Solver()
    for variables in (left, right):
        for predicate, domain in domains.items():
            solver.add(variables[predicate] >= 0, variables[predicate] < len(domain))
        solver.add(*_z3_feasibility(ontology, variables, domains))
        solver.add(*_z3_derivations(graph, variables, domains))
    solver.add(*_z3_observation_equal(operators, left, right, domains))
    left_decisions = {
        guideline["id"]: _z3_decision(guideline, left, domains, ontology)
        for guideline in guidelines
    }
    right_decisions = {
        guideline["id"]: _z3_decision(guideline, right, domains, ontology)
        for guideline in guidelines
    }
    solver.add(
        z3.Or(*(left_decisions[item] != right_decisions[item] for item in sorted(left_decisions)))
    )
    if solver.check() != z3.sat:
        return None
    model = solver.model()

    def state(variables: dict[str, z3.ArithRef]) -> dict[str, Any]:
        return {
            predicate: predicate_map[predicate]["allowed_values"][
                model.eval(variables[predicate]).as_long()
            ]
            for predicate in sorted(variables)
        }

    left_state = state(left)
    right_state = state(right)
    action_left = {guideline["id"]: _decision(guideline, left_state) for guideline in guidelines}
    action_right = {guideline["id"]: _decision(guideline, right_state) for guideline in guidelines}
    differing = sorted(item for item in action_left if action_left[item] != action_right[item])
    return {
        "left": {"values": left_state},
        "right": {"values": right_state},
        "differing_guidelines": differing,
        "left_actions": {item: action_left[item] for item in differing},
        "right_actions": {item: action_right[item] for item in differing},
    }


def _symbolic_optimum(
    candidates: list[str],
    required: set[str],
    operator_map: dict[str, dict[str, Any]],
    weight: Decimal,
    ontology: dict[str, Any],
    guidelines: list[dict[str, Any]],
    graph: dict[str, Any],
) -> tuple[Decimal, int, list[str]] | None:
    if len(candidates) > 24:
        raise CertificateVerificationError("independent optimum is limited to 24 operators")
    best: tuple[Decimal, int, tuple[str, ...]] | None = None
    for flags in itertools.product((False, True), repeat=len(candidates)):
        ids = {item for item, enabled in zip(candidates, flags, strict=True) if enabled}
        if not required.issubset(ids) or not _scheme_valid(ids, operator_map):
            continue
        selected = [operator_map[item] for item in sorted(ids)]
        if _symbolic_counterexample(ontology, guidelines, selected, graph) is not None:
            continue
        key = (_scheme_cost(ids, operator_map, weight), len(ids), tuple(sorted(ids)))
        if best is None or key < best:
            best = key
    return None if best is None else (best[0], best[1], list(best[2]))


def verify_certificate(path: str | Path) -> VerificationReport:
    """Recompute certificate claims from raw authoritative source files."""

    certificate_path = Path(path).resolve()
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    if certificate.get("schema_version") != "1.1":
        raise CertificateVerificationError("only certificate schema 1.1 is accepted")
    if certificate.get("semantic_contract") != "action-only-decision-sufficiency-v1.1":
        raise CertificateVerificationError("semantic contract mismatch")
    expected_assumptions = [
        "finite declared predicate domains",
        "None alone denotes unknown evidence",
        "typed scalar identity distinguishes booleans, integers, numbers, and strings",
        "only declared feasibility and deterministic unary derivations constrain states",
        "synthetic fixtures are not clinical rules or measured costs",
    ]
    if certificate.get("assumptions") != expected_assumptions:
        raise CertificateVerificationError("semantic assumptions mismatch")
    body = dict(certificate)
    claimed_hash = body.pop("certificate_hash", None)
    claimed_checksum = body.pop("content_checksum", None)
    actual = _json_hash(body)
    if claimed_hash != actual or claimed_checksum != actual:
        raise CertificateVerificationError(
            f"content checksum mismatch: claimed {claimed_checksum}, computed {actual}"
        )
    checks = ["content_checksum", "semantic_contract"]

    root, project_path = _root_for(certificate_path, certificate["project_config"])
    for source in certificate["source_hashes"]:
        source_path = Path(source["path"])
        resolved = source_path if source_path.is_absolute() else root / source_path
        if not resolved.is_file() or _file_hash(resolved) != source["sha256"]:
            raise CertificateVerificationError(f"source hash mismatch for {source['path']}")
    checks.append("source_hashes")

    project = _load_yaml(project_path)
    if project["project_id"] != certificate["project_id"]:
        raise CertificateVerificationError("project ID mismatch")
    base = project_path.parent
    ontology_path = (base / project["ontology"]).resolve()
    operator_path = (base / project["operators"]).resolve()
    graph_path = (base / project["derivations"]).resolve()
    guideline_paths = [(base / item).resolve() for item in project["guidelines"]]
    ontology = _load_yaml(ontology_path)
    operators = _load_yaml(operator_path)
    graph = _load_yaml(graph_path)
    bundles = [_load_yaml(item) for item in guideline_paths]
    guidelines = [item for bundle in bundles for item in bundle["guidelines"]]
    expected_guideline_hashes = {
        f"{guideline['id']}@{guideline['version']}": _file_hash(path_item)
        for path_item, bundle in zip(guideline_paths, bundles, strict=True)
        for guideline in bundle["guidelines"]
    }
    if (
        certificate["ontology_hash"] != _file_hash(ontology_path)
        or certificate["operator_catalogue_hash"] != _file_hash(operator_path)
        or certificate["derivation_graph_hash"] != _file_hash(graph_path)
        or certificate["guideline_hashes"] != expected_guideline_hashes
        or certificate["feasibility_hash"]
        != _json_hash(ontology.get("feasibility", {"schema_version": "1.0", "constraints": []}))
        or certificate["decision_program_hash"] != _json_hash(_decision_program(guidelines))
    ):
        raise CertificateVerificationError("semantic hash payload mismatch")
    checks.append("semantic_hashes")

    operator_map = {item["id"]: item for item in operators["operators"]}
    available = _available(project, operators, include_repair=False)
    selected_ids = certificate["selected_operators"]
    selected_set = set(selected_ids)
    if selected_ids != sorted(selected_set):
        raise CertificateVerificationError("selected operators are not unique and sorted")
    if not selected_set.issubset(operator_map):
        raise CertificateVerificationError("selected operators are not declared")
    closure = _operator_closure(selected_set, operator_map)
    expected_closure = {
        "selected": selected_ids,
        "required": sorted(closure - selected_set),
        "derived_predicates": certificate["derived_predicates"],
    }
    if certificate["operator_closure"] != expected_closure:
        raise CertificateVerificationError("operator closure mismatch")

    kind = certificate["certificate_type"]
    expected_scope = (
        "BOUNDED"
        if kind == "OUT_OF_SPEC"
        else "SMT_UNIVERSAL"
        if certificate["solver"] == "separation"
        else "FINITE_EXHAUSTIVE"
    )
    if certificate.get("proof_scope") != expected_scope:
        raise CertificateVerificationError("proof scope mismatch")
    if kind == "OUT_OF_SPEC":
        expected_findings = _expected_oos(ontology, guidelines, set(project["target_modalities"]))
        if certificate["findings"] != expected_findings:
            raise CertificateVerificationError("OUT_OF_SPEC findings mismatch")
        if (
            selected_ids
            or certificate["derived_predicates"]
            or certificate["action_distinction_count"] != 0
            or Decimal(str(certificate["total_cost"])) != 0
            or certificate["objective_tuple"] != ["0", 0, []]
            or any(certificate["optimality"].values())
            or certificate["solver_status"] != "INFEASIBLE"
            or certificate["verification"]
            != {
                "method": "z3-and-finite-bruteforce",
                "no_counterexample_expected": False,
                "finite_state_count": None,
                "required_pair_count": 0,
                "optimality_claimed": False,
                "seed": int(project.get("seed", 0)),
            }
        ):
            raise CertificateVerificationError("OUT_OF_SPEC base payload mismatch")
        checks.append("oos_recomputed")
        return VerificationReport(valid=True, certificate_type=kind, checks=checks)

    if expected_scope == "SMT_UNIVERSAL":
        selected = [operator_map[item] for item in selected_ids]
        actual_derived = _derived_predicates(selected, graph)
        if certificate["derived_predicates"] != actual_derived:
            raise CertificateVerificationError("derived predicate payload mismatch")
        if certificate["action_distinction_count"] is not None:
            raise CertificateVerificationError("symbolic action distinction count must be null")
        verification = certificate["verification"]
        if verification != {
            "method": "z3-counterexample-separation",
            "no_counterexample_expected": kind == "EXECUTABLE",
            "finite_state_count": None,
            "required_pair_count": None,
            "optimality_claimed": certificate["optimality"]["claimed"],
            "seed": int(project.get("seed", 0)),
        }:
            raise CertificateVerificationError("symbolic verification payload mismatch")
        weight = Decimal(str(project.get("instability_weight", 0)))
        actual_cost = _scheme_cost(selected_set, operator_map, weight)
        objective = certificate["objective_tuple"]
        if (
            Decimal(str(certificate["total_cost"])) != actual_cost
            or Decimal(str(objective[0])) != actual_cost
            or objective[1] != len(selected_ids)
            or objective[2] != selected_ids
        ):
            raise CertificateVerificationError("objective tuple mismatch")
        claimed_optimality = certificate["optimality"]["claimed"]
        if any(
            certificate["optimality"][item] != claimed_optimality
            for item in ("cost_proven", "count_proven", "lexical_proven")
        ):
            raise CertificateVerificationError("optimality tier payload mismatch")
        if kind == "EXECUTABLE":
            expected_programs = {
                guideline["id"]: sorted(rule["id"] for rule in guideline["rules"])
                for guideline in guidelines
            }
            expected_guidelines = sorted(
                f"{guideline['id']}@{guideline['version']}" for guideline in guidelines
            )
            expected_clauses = sorted(
                f"{guideline['id']}:{rule['id']}"
                for guideline in guidelines
                for rule in guideline["rules"]
            )
            if (
                certificate["action_programs"] != expected_programs
                or certificate["guidelines_covered"] != expected_guidelines
                or certificate["clauses_covered"] != expected_clauses
            ):
                raise CertificateVerificationError("action program payload mismatch")
            if not selected_set.issubset(available) or not _scheme_valid(
                selected_set, operator_map
            ):
                raise CertificateVerificationError(
                    "selected scheme violates availability/prerequisites"
                )
            if _symbolic_counterexample(ontology, guidelines, selected, graph) is not None:
                raise CertificateVerificationError("selected scheme is not decision sufficient")
            if claimed_optimality:
                if certificate["solver_status"] != "OPTIMAL":
                    raise CertificateVerificationError("solver status contradicts optimality")
                optimum = _symbolic_optimum(
                    available,
                    set(project.get("required_operators", [])),
                    operator_map,
                    weight,
                    ontology,
                    guidelines,
                    graph,
                )
                claimed = (Decimal(str(objective[0])), objective[1], objective[2])
                if optimum != claimed:
                    raise CertificateVerificationError("optimality tuple mismatch")
            checks.extend(["symbolic_decision_sufficiency", "symbolic_optimum"])
        elif kind == "INCOMPLETE":
            all_available = [operator_map[item] for item in available]
            if _symbolic_counterexample(ontology, guidelines, all_available, graph) is None:
                raise CertificateVerificationError("INCOMPLETE claim is unsound")
            claimed_counterexamples = certificate["uncovered_counterexamples"]
            if not claimed_counterexamples:
                raise CertificateVerificationError("INCOMPLETE counterexamples are empty")
            referenced = set(_reference_clauses(guidelines))
            symbolic_missing: set[str] = set()
            for witness in claimed_counterexamples:
                left_state = witness["left"]["values"]
                right_state = witness["right"]["values"]
                if (
                    set(left_state) != set(_z3_domains(ontology))
                    or set(right_state) != set(_z3_domains(ontology))
                    or not _feasible(ontology, left_state)
                    or not _feasible(ontology, right_state)
                    or not _derivations_consistent(graph, left_state)
                    or not _derivations_consistent(graph, right_state)
                    or _observation(all_available, graph, left_state)
                    != _observation(all_available, graph, right_state)
                ):
                    raise CertificateVerificationError("symbolic counterexample is invalid")
                left_actions = {
                    guideline["id"]: _decision(guideline, left_state) for guideline in guidelines
                }
                right_actions = {
                    guideline["id"]: _decision(guideline, right_state) for guideline in guidelines
                }
                differing = sorted(
                    item for item in left_actions if left_actions[item] != right_actions[item]
                )
                expected_witness = {
                    "left": {"values": left_state},
                    "right": {"values": right_state},
                    "differing_guidelines": differing,
                    "left_actions": {item: left_actions[item] for item in differing},
                    "right_actions": {item: right_actions[item] for item in differing},
                }
                if not differing or witness != expected_witness:
                    raise CertificateVerificationError("symbolic counterexample payload mismatch")
                symbolic_missing.update(
                    item for item in referenced if not _equal(left_state[item], right_state[item])
                )
            if certificate["missing_predicates"] != sorted(symbolic_missing):
                raise CertificateVerificationError("missing predicate payload mismatch")
            repair_ids = _available(project, operators, include_repair=True)
            unavailable = [item for item in repair_ids if item not in available]
            symbolic_best: tuple[Decimal, int, tuple[str, ...]] | None = None
            base_set = set(available)
            for flags in itertools.product((False, True), repeat=len(unavailable)):
                additions = {
                    item for item, enabled in zip(unavailable, flags, strict=True) if enabled
                }
                scheme = base_set | additions
                if not _scheme_valid(scheme, operator_map):
                    continue
                selected_scheme = [operator_map[item] for item in sorted(scheme)]
                if (
                    _symbolic_counterexample(ontology, guidelines, selected_scheme, graph)
                    is not None
                ):
                    continue
                key = (
                    _scheme_cost(additions, operator_map, weight),
                    len(additions),
                    tuple(sorted(additions)),
                )
                if symbolic_best is None or key < symbolic_best:
                    symbolic_best = key
            if symbolic_best is None:
                if (
                    certificate["minimal_additions"]
                    or certificate["minimum_repair_cost"] is not None
                ):
                    raise CertificateVerificationError("repair payload claims a nonexistent repair")
            elif list(symbolic_best[2]) != certificate["minimal_additions"] or symbolic_best[
                0
            ] != Decimal(str(certificate["minimum_repair_cost"])):
                raise CertificateVerificationError("incremental repair mismatch")
            if certificate["solver_status"] != "INFEASIBLE":
                raise CertificateVerificationError("INCOMPLETE solver status mismatch")
            checks.extend(["symbolic_incomplete", "symbolic_incremental_repair"])
        else:
            raise CertificateVerificationError(f"unsupported certificate type {kind!r}")
        return VerificationReport(valid=True, certificate_type=kind, checks=checks)

    states = _states(ontology, graph, int(project.get("max_states", 100000)))
    selected = [operator_map[item] for item in selected_ids]
    actual_derived = _derived_predicates(selected, graph)
    if certificate["derived_predicates"] != actual_derived:
        raise CertificateVerificationError("derived predicate payload mismatch")
    executable, distinctions = _rows(states, guidelines, selected, graph)
    if distinctions != certificate["action_distinction_count"]:
        raise CertificateVerificationError("action distinction count mismatch")
    checks.append("action_distinctions")
    verification = certificate["verification"]
    if (
        verification["method"] != "z3-and-finite-bruteforce"
        or verification["finite_state_count"] != len(states)
        or verification["required_pair_count"] != distinctions
        or verification["no_counterexample_expected"] != (kind == "EXECUTABLE")
        or verification["optimality_claimed"] != certificate["optimality"]["claimed"]
        or verification["seed"] != int(project.get("seed", 0))
    ):
        raise CertificateVerificationError("verification payload mismatch")
    checks.append("verification_payload")

    weight = Decimal(str(project.get("instability_weight", 0)))
    actual_cost = _scheme_cost(selected_set, operator_map, weight)
    objective = certificate["objective_tuple"]
    if (
        Decimal(str(certificate["total_cost"])) != actual_cost
        or Decimal(str(objective[0])) != actual_cost
        or objective[1] != len(selected_ids)
        or objective[2] != selected_ids
    ):
        raise CertificateVerificationError("objective tuple mismatch")
    checks.append("objective_tuple")
    claimed_optimality = certificate["optimality"]["claimed"]
    if any(
        certificate["optimality"][item] != claimed_optimality
        for item in ("cost_proven", "count_proven", "lexical_proven")
    ):
        raise CertificateVerificationError("optimality tier payload mismatch")

    if kind == "EXECUTABLE":
        expected_programs = {
            guideline["id"]: sorted(rule["id"] for rule in guideline["rules"])
            for guideline in guidelines
        }
        expected_guidelines = sorted(
            f"{guideline['id']}@{guideline['version']}" for guideline in guidelines
        )
        expected_clauses = sorted(
            f"{guideline['id']}:{rule['id']}"
            for guideline in guidelines
            for rule in guideline["rules"]
        )
        if (
            certificate["action_programs"] != expected_programs
            or certificate["guidelines_covered"] != expected_guidelines
            or certificate["clauses_covered"] != expected_clauses
        ):
            raise CertificateVerificationError("action program payload mismatch")
        if not selected_set.issubset(available) or not _scheme_valid(selected_set, operator_map):
            raise CertificateVerificationError(
                "selected scheme violates availability/prerequisites"
            )
        if not executable:
            raise CertificateVerificationError("selected scheme is not decision sufficient")
        if certificate["optimality"]["claimed"]:
            if certificate["solver_status"] != "OPTIMAL":
                raise CertificateVerificationError("solver status contradicts optimality")
            optimum = _optimum(
                available,
                set(project.get("required_operators", [])),
                operator_map,
                weight,
                states,
                guidelines,
                graph,
            )
            claimed = (Decimal(str(objective[0])), objective[1], objective[2])
            if optimum != claimed or not all(
                certificate["optimality"][item]
                for item in ("cost_proven", "count_proven", "lexical_proven")
            ):
                raise CertificateVerificationError("optimality tuple mismatch")
            checks.append("independent_optimum")
        checks.append("decision_sufficiency")
    elif kind == "INCOMPLETE":
        all_available = [operator_map[item] for item in available]
        if _rows(states, guidelines, all_available, graph)[0]:
            raise CertificateVerificationError("INCOMPLETE claim is unsound")
        counterexamples, missing = _uncovered_counterexamples(
            states, guidelines, all_available, graph
        )
        claimed_counterexamples = certificate["uncovered_counterexamples"]
        if not claimed_counterexamples:
            raise CertificateVerificationError("INCOMPLETE counterexamples are empty")
        if certificate["solver"] in {"exact", "greedy"}:
            if claimed_counterexamples != counterexamples[:10]:
                raise CertificateVerificationError("uncovered counterexamples mismatch")
        elif any(item not in counterexamples for item in claimed_counterexamples):
            raise CertificateVerificationError("uncovered counterexample is not valid")
        if certificate["missing_predicates"] != missing:
            raise CertificateVerificationError("missing predicate payload mismatch")
        if certificate["solver_status"] != "INFEASIBLE":
            raise CertificateVerificationError("INCOMPLETE solver status mismatch")
        repair_ids = _available(project, operators, include_repair=True)
        unavailable = [item for item in repair_ids if item not in available]
        best: tuple[Decimal, int, tuple[str, ...]] | None = None
        base_set = set(available)
        for flags in itertools.product((False, True), repeat=len(unavailable)):
            additions = {
                item
                for item, selected_flag in zip(unavailable, flags, strict=True)
                if selected_flag
            }
            scheme = base_set | additions
            if not _scheme_valid(scheme, operator_map):
                continue
            if not _rows(
                states, guidelines, [operator_map[item] for item in sorted(scheme)], graph
            )[0]:
                continue
            key = (
                _scheme_cost(additions, operator_map, weight),
                len(additions),
                tuple(sorted(additions)),
            )
            if best is None or key < best:
                best = key
        claimed_additions = certificate["minimal_additions"]
        claimed_repair_cost = certificate["minimum_repair_cost"]
        if best is None:
            if claimed_additions or claimed_repair_cost is not None:
                raise CertificateVerificationError("repair payload claims a nonexistent repair")
        elif list(best[2]) != claimed_additions or best[0] != Decimal(str(claimed_repair_cost)):
            raise CertificateVerificationError("incremental repair mismatch")
        checks.extend(["incomplete_recomputed", "incremental_repair"])
    else:
        raise CertificateVerificationError(f"unsupported certificate type {kind!r}")

    return VerificationReport(valid=True, certificate_type=kind, checks=checks)
