"""Bounded workflow declarations; these contracts do not execute agents."""

from typing import Annotated, Literal, Self

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
    """Legacy graph-only declaration; never implies complete execution bindings."""

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


BindingKind = Literal["question", "documents", "plan", "evidence", "answer", "check"]
OutputPort = Literal["plan", "evidence", "answer", "check"]


def role_output_ports(role: AgentRole) -> tuple[OutputPort, ...]:
    """Canonical output names/types shared with the role-output contracts."""
    ports: dict[AgentRole, tuple[OutputPort, ...]] = {
        "coordinator": ("plan",),
        "retrieval": ("evidence",),
        "reasoning": ("answer", "evidence"),
        "checking": ("check", "evidence"),
    }
    return ports[role]


class TaskBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: Literal["task"] = "task"
    field: Literal["question", "documents"]


class NodeOutputBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: Literal["node"] = "node"
    node_id: Identifier
    output: OutputPort


class InputBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: Identifier
    kind: BindingKind
    value: Annotated[TaskBinding | NodeOutputBinding, Field(discriminator="source")]


class BoundWorkflowNode(WorkflowNode):
    """Input slots are named; outputs have fixed role-specific ports/types."""

    inputs: tuple[InputBinding, ...] = Field(min_length=1, max_length=32)


class BoundWorkflow(BaseModel):
    """Complete v2 declaration; validation performs no model/tool effects.

    A task binding can access only question/documents. Predecessor bindings can
    access only canonical output ports, never arbitrary attributes or paths.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["workflow-v2"] = "workflow-v2"
    workflow_id: Identifier
    nodes: tuple[BoundWorkflowNode, ...] = Field(min_length=1, max_length=12)
    final_node_id: Identifier

    def _graph(self) -> Workflow:
        return Workflow(
            workflow_id=self.workflow_id,
            nodes=tuple(
                WorkflowNode(
                    node_id=node.node_id,
                    role=node.role,
                    instructions=node.instructions,
                    depends_on=node.depends_on,
                )
                for node in self.nodes
            ),
            final_node_id=self.final_node_id,
        )

    def topological_order(self) -> tuple[str, ...]:
        return self._graph().topological_order()

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        self._graph()  # Preserve all v1 structural guarantees before resolving ports.
        nodes = {node.node_id: node for node in self.nodes}
        for node in self.nodes:
            if len({binding.name for binding in node.inputs}) != len(node.inputs):
                raise ValueError("Input slot names must be unique within a node.")
            referenced: set[str] = set()
            kinds = {binding.kind for binding in node.inputs}
            for binding in node.inputs:
                value = binding.value
                if isinstance(value, TaskBinding):
                    if binding.kind != value.field:
                        raise ValueError("Task binding kind must match its field.")
                else:
                    if value.node_id not in node.depends_on:
                        raise ValueError("Output bindings must name declared direct predecessors.")
                    if value.output not in role_output_ports(nodes[value.node_id].role):
                        raise ValueError(
                            "The predecessor does not expose the requested output port."
                        )
                    if binding.kind != value.output:
                        raise ValueError("Input and output binding types must match.")
                    referenced.add(value.node_id)
            if referenced != set(node.depends_on):
                raise ValueError("Every dependency must supply at least one input binding.")
            if "question" not in kinds:
                raise ValueError("Every node requires a current-task question binding.")
            if node.role == "retrieval" and "documents" not in kinds:
                raise ValueError("Retrieval requires current-task documents.")
            if node.role in ("reasoning", "checking") and not kinds & {"documents", "evidence"}:
                raise ValueError("Reasoning/checking requires documents or evidence.")
            if node.role == "checking" and "answer" not in kinds:
                raise ValueError("Checking requires a predecessor answer.")
        if nodes[self.final_node_id].role != "reasoning":
            raise ValueError("The final node must expose a reasoning answer.")
        return self
