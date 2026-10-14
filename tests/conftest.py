"""Small local fixtures; no real model or scientific dataset is contacted."""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ModelBinding


@pytest.fixture
def model_binding() -> ModelBinding:
    return ModelBinding(
        model_name="test-model:latest",
        model_digest="a" * 64,
        ollama_version="test-version",
        native_context_tokens=8192,
        tokenizer_sha256="b" * 64,
        template_sha256="c" * 64,
        model_metadata_sha256="d" * 64,
    )


@pytest.fixture
def inference_profile() -> InferenceProfile:
    return InferenceProfile(num_ctx=64, num_predict=8, seed=2609)


@pytest.fixture
def request_budget() -> RequestBudget:
    return RequestBudget(
        max_model_calls=3,
        max_input_tokens=256,
        max_output_tokens=24,
        max_tool_calls=2,
        max_wall_seconds=10.0,
        max_plan_repairs=1,
        max_fallback_plans=1,
    )


@pytest.fixture
def ollama_fixture() -> Iterator[tuple[httpx.Client, dict[str, Any]]]:
    state: dict[str, Any] = {
        "calls": [],
        "digest": "a" * 64,
        "version": "test-version",
        "show": {
            "model_info": {
                "general.architecture": "test",
                "test.context_length": 8192,
                "tokenizer.ggml.tokens": ["test", "token"],
            },
            "template": "{{ .Prompt }}",
            "parameters": "temperature 0",
        },
        "generation": {
            "model": "test-model:latest",
            "response": "OK",
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 2,
            "total_duration": 500_000_000,
            "load_duration": 100_000_000,
        },
    }

    def handle(request: httpx.Request) -> httpx.Response:
        state["calls"].append(
            (
                request.method,
                request.url.path,
                json.loads(request.content) if request.content else None,
            )
        )
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": state["version"]})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "test-model:latest", "digest": state["digest"]}]}
            )
        if request.url.path == "/api/show":
            return httpx.Response(200, json=state["show"])
        if request.url.path == "/api/generate":
            return httpx.Response(200, json=state["generation"])
        raise AssertionError(f"Unexpected fixture request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        yield client, state
