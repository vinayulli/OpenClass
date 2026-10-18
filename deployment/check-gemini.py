"""Live Gemini and dynamic workflow smoke test. Never prints credentials."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv, dotenv_values
from gemini_diagnostics import describe_error


async def main():
    load_dotenv(ROOT / ".env")
    print(f"Python: {sys.executable}")
    file_key = dotenv_values(ROOT / ".env").get("GEMINI_API_KEY")
    if file_key and os.getenv("GEMINI_API_KEY") != file_key:
        print("WARNING: An inherited GEMINI_API_KEY overrides the different key in .env. Clear the shell variable to test the .env key.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    print(f"Model: {model}; authentication: GEMINI_API_KEY; endpoint: Gemini Developer API")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing from the project .env")
    os.environ.pop("GOOGLE_API_KEY", None)
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}:
        raise RuntimeError("This API-key test requires GOOGLE_GENAI_USE_VERTEXAI=false")
    from google import genai
    from google.genai import types
    from google.adk.runners import InMemoryRunner
    from backend.agents.runner import build_agent

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        response = await asyncio.wait_for(client.aio.models.generate_content(
            model=model, contents="Reply with exactly OPENCLASS_OK.",
            config=types.GenerateContentConfig(max_output_tokens=128)), timeout=60)
        if not response.text or "OPENCLASS_OK" not in response.text:
            raise RuntimeError("Gemini responded but did not return the expected marker")
        print(f"PASS: direct Gemini API request ({model})")
    finally:
        await client.aio.aclose()
        client.close()

    context = {"question": "Briefly explain what a Python function is.", "curriculum": {"name": "Python", "materials": [], "concepts": [], "objectives": []}}
    sink = {}
    runner = InMemoryRunner(agent=build_agent("tutor", context=context, result_sink=sink), app_name="openclass_smoke")
    try:
        session = await runner.session_service.create_session(app_name="openclass_smoke", user_id="synthetic_smoke_user")
        async def run():
            async for _ in runner.run_async(user_id=session.user_id, session_id=session.id, new_message=types.Content(role="user", parts=[types.Part(text=context["question"])])):
                pass
        await asyncio.wait_for(run(), timeout=120)
        if not sink.get("result", {}).get("message"):
            raise RuntimeError("Workflow did not return a validated response")
        print("PASS: dynamic Learning Coach workflow -> Gemini -> validated response")
        print("Uses a synthetic in-memory session; database, scoped tools and managed memory were not tested.")
    finally:
        await runner.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(describe_error(error), file=sys.stderr)
        sys.exit(1)
