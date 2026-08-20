from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import z3

from g2lc.errors import CertificateVerificationError
from g2lc_verifier.verifier import (
    _available,
    _decision,
    _derivations_consistent,
    _derived_predicates,
    _derived_values,
    _expected_oos,
    _expression,
    _expression_predicates,
    _feasible,
    _load_yaml,
    _normalized_expression,
    _observation,
    _operator_closure,
    _optimum,
    _root_for,
    _rows,
    _scheme_cost,
    _scheme_valid,
    _states,
    _typed_key,
    _uncovered_counterexamples,
    _z3_derivations,
    _z3_domains,
    _z3_expression,
    _z3_feasibility,
)


@pytest.mark.parametrize(
    ("value", "key"),
    [
        (None, "null:"),
        (False, "bool:false"),
        ("1", "str:1"),
        (1, "int:1"),
        (1.0, "float:1.0"),
    ],
)
def test_independent_typed_scalar_keys(value: object, key: str) -> None:
    assert _typed_key(value) == key
    with pytest.raises(CertificateVerificationError, match="non-scalar"):
        _typed_key([])


def test_independent_source_loading_and_root_resolution(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("key: value\n", encoding="utf-8")
    assert _load_yaml(mapping) == {"key": "value"}
    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- value\n", encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="not a mapping"):
        _load_yaml(sequence)
    assert _root_for(tmp_path / "certificate.json", str(mapping)) == (tmp_path, mapping)
    nested = tmp_path / "nested"
    nested.mkdir()
    assert _root_for(nested / "certificate.json", "mapping.yaml") == (tmp_path, mapping)
    with pytest.raises(CertificateVerificationError, match="cannot resolve"):
        _root_for(nested / "certificate.json", "missing.yaml")


def _raw_ontology(constraint: dict[str, object]) -> dict[str, object]:
    return {
        "predicates": [
            {"id": "a", "allowed_values": [False, True]},
            {"id": "b", "allowed_values": [False, True]},
        ],
        "feasibility": {"schema_version": "1.0", "constraints": [constraint]},
    }


@pytest.mark.parametrize(
    ("constraint", "state", "expected"),
    [
        (
            {
                "kind": "implication",
                "if": {"predicate": "a", "equals": True},
                "then": {"predicate": "b", "equals": True},
            },
            {"a": True, "b": False},
            False,
        ),
        (
            {
                "kind": "mutual_exclusion",
                "conditions": [
                    {"predicate": "a", "equals": True},
                    {"predicate": "b", "equals": True},
                ],
            },
            {"a": True, "b": True},
            False,
        ),
        (
            {
                "kind": "at_most_one",
                "conditions": [
                    {"predicate": "a", "equals": True},
                    {"predicate": "b", "equals": True},
                ],
            },
            {"a": True, "b": True},
            False,
        ),
        (
            {
                "kind": "exactly_one",
                "conditions": [
                    {"predicate": "a", "equals": True},
                    {"predicate": "b", "equals": True},
                ],
            },
            {"a": False, "b": False},
            False,
        ),
        (
            {
                "kind": "conditional_allowed",
                "if": {"predicate": "a", "equals": True},
                "predicate": "b",
                "allowed_values": [True],
            },
            {"a": True, "b": False},
            False,
        ),
        (
            {
                "kind": "derived_equality",
                "source_predicate": "a",
                "target_predicate": "b",
                "value_mapping": {"bool:false": True, "bool:true": False},
            },
            {"a": True, "b": True},
            False,
        ),
        (
            {
                "kind": "parent_child",
                "parent_predicate": "a",
                "child_predicate": "b",
                "when_parent_values": [True],
                "allowed_child_values": [True],
            },
            {"a": True, "b": False},
            False,
        ),
    ],
)
def test_independent_feasibility_rejects_each_constraint(
    constraint: dict[str, object], state: dict[str, object], expected: bool
) -> None:
    assert _feasible(_raw_ontology(constraint), state) is expected
    assert _feasible(_raw_ontology(constraint), {"a": False, "b": True}) is True


def test_independent_feasibility_rejects_unknown_kind() -> None:
    with pytest.raises(CertificateVerificationError, match="unsupported feasibility"):
        _feasible(_raw_ontology({"kind": "unknown"}), {"a": False, "b": False})


def test_independent_derivation_and_state_universe() -> None:
    graph = {
        "rules": [
            {
                "id": "a_to_b",
                "input_predicates": ["a"],
                "output_predicates": ["b"],
                "value_mapping": {"bool:false": False, "bool:true": True},
            }
        ]
    }
    ontology = {
        "predicates": [
            {"id": "a", "allowed_values": [False, True]},
            {"id": "b", "allowed_values": [False, True]},
        ]
    }
    assert _derivations_consistent(graph, {"a": True, "b": True}) is True
    assert _derivations_consistent(graph, {"a": True, "b": False}) is False
    malformed = {"rules": [{"input_predicates": ["a", "b"], "output_predicates": ["b"]}]}
    assert _derivations_consistent(malformed, {"a": True, "b": True}) is False
    assert _states(ontology, graph, 4) == [
        {"a": False, "b": False},
        {"a": True, "b": True},
    ]
    with pytest.raises(CertificateVerificationError, match="exceeds"):
        _states(ontology, graph, 3)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ({"all": [{"eq": ["a", 2]}, {"known": "a"}]}, True),
        ({"any": [{"eq": ["a", 1]}, {"eq": ["a", 2]}]}, True),
        ({"not": {"eq": ["a", 1]}}, True),
        ({"in": ["a", [1, 2]]}, True),
        ({"gte": ["a", 2]}, True),
        ({"lte": ["a", 2]}, True),
        ({"known": "a"}, True),
    ],
)
def test_independent_expression_language(expression: dict[str, object], expected: bool) -> None:
    assert _expression(expression, {"a": 2}) is expected


def test_independent_expression_rejects_unknown_operator() -> None:
    with pytest.raises(CertificateVerificationError, match="unsupported guideline"):
        _expression({"xor": []}, {"a": 1})


def test_independent_decision_priority_tie_and_default() -> None:
    guideline = {
        "rules": [
            {"id": "one", "priority": 10, "when": {"eq": ["a", 1]}, "then": {"d": "x"}},
            {"id": "two", "priority": 10, "when": {"eq": ["b", 1]}, "then": {"d": "x"}},
            {"id": "low", "priority": 1, "when": {"known": "a"}, "then": {"d": "low"}},
        ],
        "default_action": {"d": "default"},
    }
    assert _decision(guideline, {"a": 1, "b": 1}) == '[{"values":{"d":"x"}}]'
    assert _decision(guideline, {"a": None, "b": 0}) == '[{"values":{"d":"default"}}]'
    guideline.pop("default_action")
    assert _decision(guideline, {"a": None, "b": 0}) == "[]"


def test_independent_observation_derivation_and_prerequisites() -> None:
    prerequisite = {
        "id": "quality",
        "output_predicates": ["a"],
        "cost": "1",
        "modalities": ["CFP"],
    }
    operator = {
        "id": "label",
        "output_predicates": ["b"],
        "value_mappings": {"b": {"bool:false": "no", "bool:true": "yes"}},
        "required_operator_ids": ["quality"],
        "required_evidence_conditions": [{"predicate_id": "a", "allowed_values": [True]}],
        "cost": "2",
        "instability": "0.5",
        "modalities": ["CFP"],
    }
    derived_source = {
        "id": "source",
        "output_predicates": ["a"],
        "cost": "1",
        "modalities": ["CFP"],
    }
    graph = {
        "rules": [
            {
                "id": "a_to_b",
                "input_predicates": ["a"],
                "output_predicates": ["b"],
                "value_mapping": {"bool:false": False, "bool:true": True},
            }
        ]
    }
    values, direct = _derived_values([derived_source], graph, {"a": True, "b": False})
    assert values == {"a": True, "b": True}
    assert direct == {"a"}
    assert _derived_predicates([derived_source], graph) == ["a", "b"]
    assert "$derived" in _observation([derived_source], graph, {"a": True, "b": False})
    assert '$applicable",false' in _observation([operator], {}, {"a": False, "b": True})
    assert "yes" in _observation([operator], {}, {"a": True, "b": True})

    operator_map: dict[str, dict[str, Any]] = {
        "quality": prerequisite,
        "label": operator,
    }
    assert _operator_closure({"label"}, operator_map) == {"quality", "label"}
    assert _scheme_valid({"quality", "label"}, operator_map) is True
    assert _scheme_valid({"label"}, operator_map) is False
    assert _scheme_cost({"quality", "label"}, operator_map, Decimal("2")) == Decimal("4")


def test_independent_availability_rows_and_optimum() -> None:
    project = {"target_modalities": ["CFP"], "forbidden_operators": ["forbidden"]}
    operators = {
        "operators": [
            {"id": "a", "modalities": ["CFP"], "output_predicates": ["a"], "cost": 1},
            {
                "id": "b",
                "modalities": ["CFP"],
                "output_predicates": ["b"],
                "cost": 2,
                "availability": "UNAVAILABLE",
            },
            {"id": "oct", "modalities": ["OCT"], "output_predicates": [], "cost": 1},
            {"id": "forbidden", "modalities": ["CFP"], "output_predicates": [], "cost": 1},
            {
                "id": "missing_dep",
                "modalities": ["CFP"],
                "required_operator_ids": ["unknown"],
                "output_predicates": [],
                "cost": 1,
            },
        ]
    }
    assert _available(project, operators, include_repair=False) == ["a"]
    assert _available(project, operators, include_repair=True) == ["a", "b"]
    operator_map: dict[str, dict[str, Any]] = {
        str(item["id"]): item for item in operators["operators"]
    }
    states = [{"a": False}, {"a": True}]
    guidelines = [
        {
            "rules": [
                {"id": "yes", "priority": 1, "when": {"eq": ["a", True]}, "then": {"d": "y"}}
            ],
            "default_action": {"d": "n"},
        }
    ]
    assert _rows(states, guidelines, [], {}) == (False, 1)
    assert _rows(states, guidelines, [operator_map["a"]], {}) == (True, 1)
    assert _optimum(["a"], set(), operator_map, Decimal(0), states, guidelines, {}) == (
        Decimal(1),
        1,
        ["a"],
    )
    assert _optimum([], set(), operator_map, Decimal(0), states, guidelines, {}) is None
    with pytest.raises(CertificateVerificationError, match="24 operators"):
        _optimum(["a"] * 25, set(), operator_map, Decimal(0), states, guidelines, {})


@pytest.mark.parametrize(
    "expression",
    [
        {"all": [{"eq": ["a", 1]}]},
        {"any": [{"eq": ["a", 1]}]},
        {"not": {"eq": ["a", 1]}},
        {"eq": ["a", 1]},
        {"gte": ["a", 1]},
        {"lte": ["a", 1]},
        {"in": ["a", [1]]},
        {"known": "a"},
    ],
)
def test_independent_expression_normalization(expression: dict[str, object]) -> None:
    assert "op" in _normalized_expression(expression)


def test_independent_normalization_rejects_unknown() -> None:
    with pytest.raises(CertificateVerificationError, match="unsupported guideline"):
        _normalized_expression({"xor": []})


def test_independent_reference_oos_and_uncovered_payloads() -> None:
    expression = {"all": [{"eq": ["a", True]}, {"not": {"known": "external"}}]}
    assert _expression_predicates(expression) == {"a", "external"}
    guidelines = [
        {
            "id": "g",
            "rules": [{"id": "r", "priority": 1, "when": expression, "then": {"d": "yes"}}],
            "default_action": {"d": "no"},
        }
    ]
    ontology = {
        "predicates": [
            {
                "id": "a",
                "allowed_values": [False, True],
                "modalities": ["CFP"],
                "observability": "IMAGE_OBSERVABLE",
            },
            {
                "id": "external",
                "allowed_values": [False, True],
                "modalities": ["OCT"],
                "observability": "EXTERNAL_CLINICAL",
            },
        ]
    }
    findings = _expected_oos(ontology, guidelines, {"CFP"})
    assert findings[0]["predicate_id"] == "external"
    assert findings[0]["source_clauses"] == ["g:r"]

    finite_guidelines = [
        {
            "id": "g",
            "rules": [
                {
                    "id": "r",
                    "priority": 1,
                    "when": {"eq": ["a", True]},
                    "then": {"d": "yes"},
                }
            ],
            "default_action": {"d": "no"},
        }
    ]
    counterexamples, missing = _uncovered_counterexamples(
        [{"a": False}, {"a": True}], finite_guidelines, [], {}
    )
    assert len(counterexamples) == 1
    assert missing == ["a"]


def test_independent_symbolic_expression_and_feasibility_language() -> None:
    ontology: dict[str, Any] = {
        "predicates": [
            {"id": "a", "allowed_values": [0, 1, 2]},
            {"id": "b", "allowed_values": [0, 1, 2]},
        ],
        "feasibility": {
            "constraints": [
                {
                    "kind": "implication",
                    "if": {"predicate": "a", "equals": 1},
                    "then": {"predicate": "b", "equals": 1},
                },
                {
                    "kind": "mutual_exclusion",
                    "conditions": [
                        {"predicate": "a", "equals": 1},
                        {"predicate": "b", "equals": 1},
                    ],
                },
                {
                    "kind": "at_most_one",
                    "conditions": [
                        {"predicate": "a", "equals": 2},
                        {"predicate": "b", "equals": 2},
                    ],
                },
                {
                    "kind": "exactly_one",
                    "conditions": [
                        {"predicate": "a", "equals": 0},
                        {"predicate": "a", "equals": 1},
                        {"predicate": "a", "equals": 2},
                    ],
                },
                {
                    "kind": "conditional_allowed",
                    "if": {"predicate": "a", "equals": 0},
                    "predicate": "b",
                    "allowed_values": [0, 1],
                },
                {
                    "kind": "derived_equality",
                    "source_predicate": "a",
                    "target_predicate": "b",
                    "value_mapping": {"int:0": 2, "int:1": 1, "int:2": 0},
                },
                {
                    "kind": "parent_child",
                    "parent_predicate": "a",
                    "child_predicate": "b",
                    "when_parent_values": [2],
                    "allowed_child_values": [0],
                },
            ]
        },
    }
    domains = _z3_domains(ontology)
    variables = {"a": z3.Int("symbolic_a"), "b": z3.Int("symbolic_b")}
    assert len(_z3_feasibility(ontology, variables, domains)) == 9
    for expression in (
        {"all": [{"eq": ["a", 1]}, {"known": "b"}]},
        {"any": [{"eq": ["a", 1]}, {"eq": ["b", 2]}]},
        {"not": {"eq": ["a", 0]}},
        {"in": ["a", [0, 2]]},
        {"gte": ["a", 1]},
        {"lte": ["a", 1]},
    ):
        assert isinstance(_z3_expression(expression, variables, domains, ontology), z3.BoolRef)
    with pytest.raises(CertificateVerificationError, match="unsupported guideline"):
        _z3_expression({"xor": []}, variables, domains, ontology)
    malformed = {**ontology, "feasibility": {"constraints": [{"kind": "unknown"}]}}
    with pytest.raises(CertificateVerificationError, match="unsupported feasibility"):
        _z3_feasibility(malformed, variables, domains)

    graph = {
        "rules": [
            {
                "input_predicates": ["a"],
                "output_predicates": ["b"],
                "value_mapping": {"int:0": 2, "int:1": 1, "int:2": 0},
            }
        ]
    }
    assert len(_z3_derivations(graph, variables, domains)) == 3
