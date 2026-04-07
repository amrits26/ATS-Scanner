#!/usr/bin/env python
"""
ARQ Worker launcher - Direct script to start the worker.

Usage: python run_worker.py
"""

import asyncio
import os
import sys

# Fix Windows event loop policy FIRST before importing anything else
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.jobs import WorkerSettings
from arq.worker import run_worker

if __name__ == "__main__":
    # Set Redis URL from environment or default
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    
    print("[WORKER] Starting ARQ worker...")
    print(f"[WORKER] Redis URL: {os.environ.get('REDIS_URL')}")
    print("[WORKER] Listening for jobs...")
    
    # Run the worker
    try:
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        print("\n[WORKER] Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"[WORKER] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
