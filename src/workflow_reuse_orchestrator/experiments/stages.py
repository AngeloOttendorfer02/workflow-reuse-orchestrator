"""Sequential durable work units; this does not implement the scientific stages."""

from collections.abc import Callable
from time import perf_counter
from typing import Any

from workflow_reuse_orchestrator.domain.budgets import ResourceUsage
from workflow_reuse_orchestrator.domain.outcomes import JobRecord, JobResult, JobSpec, Receipt
from workflow_reuse_orchestrator.storage import ResultStore


class JobBlockedError(ValueError):
    """An unfinished or failed identity cannot be silently replayed."""


class JobRunner:
    """Commit intent, perform one unit, then atomically save its result and receipts.

    `local` is reserved for host-owned work with no external effects. Model/tool
    exceptions are conservative unknowns. Hard-crash recovery is explicit and
    marks every in-flight unit unknown, including local units. Retry declarations
    link to failed/unknown jobs; terminal identities are never overwritten.
    """

    def __init__(
        self,
        store: ResultStore,
        *,
        progress: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        store.verify_integrity()
        self.store = store
        self._progress = progress
        self._clock = clock

    def run(
        self,
        spec: JobSpec,
        operation: Callable[[], JobResult],
        *,
        started_receipts: tuple[Receipt, ...] = (),
        completed_receipts: Callable[[JobResult], tuple[Receipt, ...]] | None = None,
        failure_usage: Callable[[], ResourceUsage] | None = None,
    ) -> JobRecord:
        record = self.store.declare_job(spec)
        if record.status in ("succeeded", "failed"):
            self._emit(spec, "resumed_completed")
            return record
        if record.status != "pending":
            raise JobBlockedError(
                f"Job {spec.job_id} is {record.status}; use an explicit retry identity."
            )
        self.store.start_job(spec.job_id, receipts=started_receipts)
        started = self._clock()
        measured_result: JobResult | None = None
        try:
            self._emit(spec, "started")
            result = operation()
            usage = result.usage.model_dump()
            usage["wall_seconds"] = max(result.usage.wall_seconds, self._clock() - started)
            result = JobResult.model_validate(result.model_dump() | {"usage": usage})
            measured_result = result
            receipts = () if completed_receipts is None else completed_receipts(result)
            record = self.store.finish_job(spec.job_id, result, receipts=receipts)
        except BaseException as exc:
            # If a result transaction failed, its rollback leaves the intent running.
            current = self.store.job(spec.job_id)
            if current is not None and current.status == "running":
                self.store.interrupt_job(
                    spec.job_id,
                    error=f"{type(exc).__name__}: {exc}",
                    elapsed_seconds=max(0.0, self._clock() - started),
                    usage=(
                        failure_usage()
                        if failure_usage is not None
                        else None
                        if measured_result is None
                        else measured_result.usage
                    ),
                )
            raise
        self._emit(spec, "completed")
        return record

    def _emit(self, spec: JobSpec, event: str) -> None:
        if self._progress is not None:
            scope = self.store.scope(spec.scope_id)
            self._progress(
                {
                    "event": event,
                    "phase": spec.phase,
                    "stage": spec.stage,
                    "job_id": spec.job_id,
                    "method_id": spec.method_id,
                    "fold_id": None if scope is None else scope.fold_id,
                    "progress": self.store.progress(run_id=None if scope is None else scope.run_id),
                }
            )
