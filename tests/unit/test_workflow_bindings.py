"""V2 bindings complement, rather than reinterpret, legacy graph declarations."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from workflow_reuse_orchestrator.config import project_root
from workflow_reuse_orchestrator.domain.workflows import BoundWorkflow, Workflow, role_output_ports


def example() -> dict[str, Any]:
    path: Path = project_root() / "examples/bound_workflow.json"
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def test_complete_graph_json_roundtrip_and_stable_order() -> None:
    workflow = BoundWorkflow.model_validate_json(json.dumps(example()))
    assert workflow.topological_order() == ("retrieve", "reason", "check", "final")
    assert BoundWorkflow.model_validate_json(workflow.model_dump_json()) == workflow


def test_v1_and_v2_are_explicitly_separate_contracts() -> None:
    payload = example()
    with pytest.raises(ValidationError):
        Workflow.model_validate_json(json.dumps(payload))
    payload["schema_version"] = "workflow-v1"
    with pytest.raises(ValidationError):
        BoundWorkflow.model_validate_json(json.dumps(payload))
    payload["schema_version"] = "workflow-v2"
    del payload["nodes"][0]["inputs"]
    with pytest.raises(ValidationError, match="inputs"):
        BoundWorkflow.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda p: p["nodes"][0]["inputs"][0]["value"].update(field="answers"), "field"),
        (lambda p: p["nodes"][0]["inputs"][0]["value"].update(source="reference"), "source"),
        (lambda p: p["nodes"][0]["inputs"][0]["value"].update(path="annotations"), "path"),
        (lambda p: p["nodes"][0]["inputs"][0].update(kind="answer"), "kind"),
        (lambda p: p["nodes"][1]["inputs"][1]["value"].update(node_id="final"), "predecessors"),
        (lambda p: p["nodes"][1]["inputs"][1]["value"].update(output="answer"), "port"),
        (lambda p: p["nodes"][1]["inputs"][1].update(kind="plan"), "types"),
        (lambda p: p["nodes"][1]["inputs"][1].update(name="question"), "unique"),
        (lambda p: p["nodes"][1].update(inputs=p["nodes"][1]["inputs"][:1]), "dependency"),
        (lambda p: p["nodes"][0].update(inputs=p["nodes"][0]["inputs"][:1]), "documents"),
        (lambda p: p["nodes"][0].update(inputs=p["nodes"][0]["inputs"][1:]), "question"),
        (lambda p: p["nodes"][2]["inputs"].pop(1), "dependency"),
        (lambda p: p["nodes"][0]["depends_on"].append("final"), "cycle"),
        (lambda p: p["nodes"][0]["depends_on"].append("missing"), "existing"),
        (lambda p: p["nodes"].append(p["nodes"][0]), "unique"),
        (lambda p: p.update(final_node_id="check"), "contribute"),
    ],
)
def test_invalid_bindings_fail_during_pure_validation(
    mutate: Callable[[dict[str, Any]], None], match: str
) -> None:
    payload = example()
    mutate(payload)
    with pytest.raises(ValidationError, match=match):
        BoundWorkflow.model_validate_json(json.dumps(payload))


def test_dependency_fan_in_is_required_and_final_port_must_be_an_answer() -> None:
    payload = example()
    payload["nodes"] = payload["nodes"][:3]
    payload["final_node_id"] = "check"
    with pytest.raises(ValidationError, match="reasoning answer"):
        BoundWorkflow.model_validate_json(json.dumps(payload))


def test_role_ports_match_the_output_contract_names() -> None:
    from workflow_reuse_orchestrator.domain.outcomes import (
        CheckingOutput,
        CoordinatorOutput,
        ReasoningOutput,
        RetrievalOutput,
    )

    for role, contract in (
        ("coordinator", CoordinatorOutput),
        ("retrieval", RetrievalOutput),
        ("reasoning", ReasoningOutput),
        ("checking", CheckingOutput),
    ):
        assert set(contract.model_fields) - {"role"} == set(role_output_ports(role))
