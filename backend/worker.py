"""
ARQ Worker entry point.

This script is used to start the background job worker:
    arq backend.worker.WorkerSettings

or from PowerShell:
    python -m arq backend.worker.WorkerSettings

The worker connects to Redis, listens for jobs, and executes them asynchronously.
"""

from .jobs import WorkerSettings

# ARQ will look for this automatically
__all__ = ["WorkerSettings"]
