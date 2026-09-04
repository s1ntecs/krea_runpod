from __future__ import annotations

import logging
import os
import traceback
import uuid

from krea_worker.errors import WorkerError
from krea_worker.service import KreaService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("krea-runpod")
SERVICE = KreaService()


def handler(job: dict) -> dict:
    job_id = str(job.get("id") or uuid.uuid4())
    payload = job.get("input", job)
    try:
        return SERVICE.process(payload, job_id)
    except WorkerError as exc:
        logger.warning("Job %s failed: %s", job_id, exc.message)
        return {"ok": False, "error": exc.as_dict()}
    except Exception as exc:
        logger.exception("Unexpected failure in job %s", job_id)
        error = {
            "code": "internal_error",
            "message": str(exc),
        }
        if SERVICE.settings.debug_errors:
            error["traceback"] = traceback.format_exc()
        return {"ok": False, "error": error}


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
