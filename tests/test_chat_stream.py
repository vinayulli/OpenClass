import asyncio
import json
from fastapi import HTTPException
from backend.chat_stream import stream_response


def test_progress_stream_orders_real_stages_and_returns_final_answer():
    async def run(progress):
        await progress("records", "Reading records")
        await progress("response", "Preparing response")
        return {"message": "Done"}
    async def collect():
        return [part async for part in stream_response(run).body_iterator]
    events = asyncio.run(collect())
    assert len(events) == 3
    assert '"stage": "records"' in events[0]
    assert '"stage": "response"' in events[1]
    assert 'event: result' in events[2]
    assert "memory" not in "".join(events)


def test_progress_stream_reports_errors_without_exposing_internal_exception():
    async def denied(progress):
        raise HTTPException(403, "Access denied")
    async def failed(progress):
        raise RuntimeError("SECRET")
    async def collect(run):
        return "".join([part async for part in stream_response(run).body_iterator])
    assert '"status": 403' in asyncio.run(collect(denied))
    assert "SECRET" not in asyncio.run(collect(failed))
