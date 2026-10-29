from app import config

_repo = None


def get_repo():
    """Return the configured repository (process-wide singleton)."""
    global _repo
    if _repo is None:
        if config.DATA_BACKEND == "memory":
            from .memory import MemoryRepo
            _repo = MemoryRepo.from_fixtures(config.FIXTURES)
        elif config.DATA_BACKEND == "local":
            from .local import LocalRepo  # WS3
            _repo = LocalRepo()
        elif config.DATA_BACKEND == "databricks":
            from .databricks import DatabricksRepo  # WS3
            _repo = DatabricksRepo()
        else:
            raise ValueError(f"Unknown DATA_BACKEND {config.DATA_BACKEND}")
    return _repo


def reset_repo():
    """Tests only."""
    global _repo
    _repo = None
