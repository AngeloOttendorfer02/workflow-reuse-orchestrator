"""Pure domain contracts cannot import execution, fitting, or result storage."""

import ast

from workflow_reuse_orchestrator.config import project_root


def test_domain_contracts_have_no_runtime_or_scientific_dependencies() -> None:
    root = project_root() / "src/workflow_reuse_orchestrator/domain"
    allowed = {"workflow_reuse_orchestrator.domain"}
    for path in root.glob("*.py"):
        syntax = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(syntax):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [name.name for name in node.names]
            else:
                continue
            for module in modules:
                if module.startswith("workflow_reuse_orchestrator"):
                    assert any(module.startswith(prefix + ".") for prefix in allowed), (
                        path,
                        module,
                    )
