import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import agents
from .store import all_of, db, initialize, put, uid, warm_database, close_database
from .services import limits, tasks

logger = logging.getLogger("openclass")


def prepare_database():
    warm_database()
    initialize()
    if os.getenv("OPENCLASS_DEMO", "true").lower() == "true":
        from mock_data.focused_demo import seed
        with db() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812417)")
            seed(conn)
            from mock_data.machine_learning import seed as seed_ml
            seed_ml(conn)
    with db() as conn:
        for job in all_of(conn, "job"):
            if job["status"] in ("queued", "running") and job.get("transport") != "a2a":
                job.update(status="failed", error="Server restarted. Please retry.")
                put(conn, "job", job)
        for item in all_of(conn, "memory_outbox"):
            if item["status"] == "processing":
                item["status"] = "pending"
                put(conn, "memory_outbox", item)


@asynccontextmanager
async def lifespan(app):
    from .cloud.config import validate_governance
    from .cloud.memory_outbox import worker
    validate_governance()
    memory_worker = None
    a2a_workers = []
    try:
        if os.getenv("OPENCLASS_DEPLOYMENT_BOOTSTRAP", "false").lower() == "true":
            # Private staging revision: check connectivity without claiming live
            # classroom jobs before workload identities/policies are installed.
            await asyncio.to_thread(warm_database)
            yield
            return
        await asyncio.to_thread(prepare_database)
        from .a2a.config import shared_secret
        from .a2a.workers import start_workers
        await asyncio.to_thread(shared_secret)
        a2a_workers = start_workers()
        memory_worker = asyncio.create_task(worker())
        from .assignments import worker as assignment_worker
        a2a_workers.append(asyncio.create_task(assignment_worker()))
        from .self_study import worker as study_worker
        a2a_workers.append(asyncio.create_task(study_worker()))
        yield
    finally:
        for worker in a2a_workers:
            worker.cancel()
        await asyncio.gather(*a2a_workers, return_exceptions=True)
        if memory_worker:
            memory_worker.cancel()
            await asyncio.gather(memory_worker, return_exceptions=True)
        pending = list(tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.to_thread(close_database)


app = FastAPI(title="OpenClass AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("OPENCLASS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","), allow_credentials=True, allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "Idempotency-Key"])


@app.middleware("http")
async def trace(request, call_next):
    trace_id = uid()
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    logger.info("request trace=%s method=%s status=%s duration_ms=%.0f", trace_id, request.method, response.status_code, (time.monotonic()-start)*1000)
    return response


@app.get("/api/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "ai_configured": agents.configured(), "demo": os.getenv("OPENCLASS_DEMO", "true").lower() == "true", "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash")}



from .routes import auth, courses, assessments, intelligence, governance, experience, activity, agent_tasks, self_study, learning_paths
from .a2a import routes as a2a_routes
from .routes.agent_coordinator import router as coordinator_router
app.include_router(coordinator_router)

for router_module in (auth, courses, assessments, intelligence, governance, experience, activity, agent_tasks, self_study, learning_paths, a2a_routes):
    app.include_router(router_module.router)

# Production serves the built React client on the same origin as the API.
from pathlib import Path
from .frontend import SPAStaticFiles
frontend_dist = Path(os.getenv("FRONTEND_DIST", "static"))
if frontend_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
