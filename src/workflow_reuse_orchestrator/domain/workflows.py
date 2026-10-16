"""Bounded workflow declarations; these contracts do not execute agents."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workflow_reuse_orchestrator.domain.tasks import Identifier, Text

AgentRole = Literal["coordinator", "retrieval", "reasoning", "checking"]


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: Identifier
    role: AgentRole
    instructions: Text
    depends_on: tuple[Identifier, ...] = ()


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["workflow-v1"] = "workflow-v1"
    workflow_id: Identifier
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1, max_length=12)
    final_node_id: Identifier

    def topological_order(self) -> tuple[str, ...]:
        """Use stable identifiers to break ties between ready nodes."""
        pending = {node.node_id: set(node.depends_on) for node in self.nodes}
        ordered: list[str] = []
        while pending:
            ready = sorted(node_id for node_id, dependencies in pending.items() if not dependencies)
            if not ready:
                raise ValueError("Workflow dependencies contain a cycle.")
            for node_id in ready:
                ordered.append(node_id)
                del pending[node_id]
            for dependencies in pending.values():
                dependencies.difference_update(ready)
        return tuple(ordered)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Workflow node identifiers must be unique.")
        if self.final_node_id not in node_ids:
            raise ValueError("The final node must exist in the workflow.")
        for node in self.nodes:
            if len(node.depends_on) != len(set(node.depends_on)):
                raise ValueError("Node dependencies must be unique.")
            if node.node_id in node.depends_on or set(node.depends_on) - node_ids:
                raise ValueError("Dependencies must name other existing workflow nodes.")
        self.topological_order()
        dependencies = {node.node_id: node.depends_on for node in self.nodes}
        ancestors = {self.final_node_id}
        pending = [self.final_node_id]
        while pending:
            for predecessor in dependencies[pending.pop()]:
                if predecessor not in ancestors:
                    ancestors.add(predecessor)
                    pending.append(predecessor)
        if ancestors != node_ids:
            raise ValueError("Every node must contribute to the final node.")
        return self
