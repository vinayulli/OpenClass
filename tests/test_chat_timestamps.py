import asyncio
from backend.routes import intelligence
from backend.schemas import Chat


def test_chat_persists_and_returns_distinct_server_timestamps(monkeypatch):
    from backend import chat_context
    saved=[]
    dates=iter(['2026-10-18T04:00:00+00:00','2026-10-18T04:00:10+00:00'])
    elapsed=iter([100.0,110.0])
    monkeypatch.setattr(intelligence,'now',lambda:next(dates))
    # Replace only this module's clock; patching shared time affects asyncio internals.
    from types import SimpleNamespace
    monkeypatch.setattr(intelligence,'time',SimpleNamespace(monotonic=lambda:next(elapsed)))
    monkeypatch.setattr(intelligence,'rate_limit',lambda *args:None)
    monkeypatch.setattr(chat_context,'build_context',lambda *args:{})
    monkeypatch.setattr(chat_context,'save_chat',lambda item:saved.append(item))
    async def answer(*args):
        return {'message':'A grounded response'}
    monkeypatch.setattr(intelligence,'ai_call',answer)
    actor={'id':'t','org':'o','role':'teacher'}
    result=asyncio.run(intelligence.run_chat('c',Chat(message='Hello'),actor))
    assert result['question_at']=='2026-10-18T04:00:00+00:00'
    assert result['response_at']=='2026-10-18T04:00:10+00:00'
    assert result['duration_ms']==10000
    assert saved[0]['question_at']==result['question_at']
    assert saved[0]['response_at']==saved[0]['at']==result['response_at']
    assert saved[0]['duration_ms']==result['duration_ms']
