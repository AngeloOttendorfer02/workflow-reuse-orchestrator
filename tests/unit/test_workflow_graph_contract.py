"""Graph contracts reject malformed, oversized, or disconnected procedures."""

import pytest

from workflow_reuse_orchestrator.domain.workflows import Workflow, WorkflowNode


def node(node_id: str, dependencies: tuple[str, ...] = ()) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id,
        role="reasoning",
        instructions="Use supplied evidence.",
        depends_on=dependencies,
    )


def test_order_is_stable_across_declaration_order() -> None:
    nodes = (node("b"), node("a"), node("final", ("b", "a")))
    first = Workflow(workflow_id="w", nodes=nodes, final_node_id="final")
    second = Workflow(workflow_id="w", nodes=tuple(reversed(nodes)), final_node_id="final")
    assert first.topological_order() == second.topological_order() == ("a", "b", "final")


@pytest.mark.parametrize(
    "nodes,final,reason",
    [
        ((node("a"), node("a")), "a", "unique"),
        ((node("a", ("missing",)),), "a", "existing"),
        ((node("a", ("a",)),), "a", "existing"),
        ((node("a", ("b",)), node("b", ("a",))), "a", "cycle"),
        ((node("a"), node("b")), "b", "contribute"),
        ((node("a"),), "missing", "final node"),
    ],
)
def test_rejects_invalid_graphs(nodes: tuple[WorkflowNode, ...], final: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        Workflow(workflow_id="w", nodes=nodes, final_node_id=final)


def test_rejects_more_than_twelve_nodes() -> None:
    nodes = tuple(node(str(index), (str(index - 1),) if index else ()) for index in range(13))
    with pytest.raises(ValueError, match="12"):
        Workflow(workflow_id="w", nodes=nodes, final_node_id="12")
