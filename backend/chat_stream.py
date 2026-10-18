"""SSE progress for real chat stages, followed by one validated response."""
import asyncio
import json
from fastapi import HTTPException
from fastapi.responses import StreamingResponse


def stream_response(run):
    async def events():
        queue = asyncio.Queue()

        async def progress(stage, message):
            await queue.put(("progress", {"stage": stage, "message": message}))

        async def execute():
            try:
                result = await run(progress)
                await queue.put(("result", result))
            except asyncio.CancelledError:
                raise
            except HTTPException as error:
                await queue.put(("error", {"message": error.detail if isinstance(error.detail, str) else "Request failed", "status": error.status_code}))
            except Exception:
                await queue.put(("error", {"message": "The assistant could not complete this request. Please retry.", "status": 502}))

        task = asyncio.create_task(execute())
        try:
            while True:
                try:
                    event, payload = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield "event: "+event+"\ndata: "+json.dumps(payload)+"\n\n"
                if event in {"result", "error"}:
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
