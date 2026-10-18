"""Capture actual specialist responses for manual rubric review, without pytest assertions."""
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from backend.agents import invoke


async def main():
    path = Path(__file__).parent
    cases = json.loads((path / "scenarios.json").read_text())["cases"]
    results = []
    for case in cases:
        try:
            result = await invoke(case["agent"], case["input"], "synthetic-eval")
            results.append({"case": case["id"], "output": result, "criteria": case["criteria"], "verdict": "human review required"})
        except Exception as error:
            results.append({"case": case["id"], "error_type": type(error).__name__, "verdict": "failed invocation"})
    target = path / "results.local.json"
    target.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} cases to {target}; review against the supplied rubrics.")


if __name__ == "__main__":
    asyncio.run(main())
