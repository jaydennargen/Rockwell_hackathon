"""@trace: mlflow.trace when mlflow is importable and MLFLOW_TRACKING_URI is set, else a no-op."""
import os


def _noop(fn=None, **_):
    return fn if fn is not None else (lambda f: f)


trace = _noop
if os.environ.get("MLFLOW_TRACKING_URI"):
    try:
        import mlflow

        trace = mlflow.trace
    except ImportError:  # pragma: no cover
        pass


def current_trace_id() -> str | None:
    if trace is _noop:
        return None
    try:
        import mlflow
        span = mlflow.get_current_active_span()
        return span.request_id if span else None
    except Exception:  # noqa: BLE001
        return None
