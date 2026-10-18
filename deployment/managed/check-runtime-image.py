"""Check the Linux image's real startup lifecycle without credentials or network.

The positive case mirrors explicit Runtime env plus its injected project. The
negative control must reject a missing location. No model/tool calls are made.
"""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    values = json.loads((ROOT/"deployment/managed/release.auto.tfvars.json").read_text())
    environment = dict(values["runtime_environment"])
    environment.pop("GOOGLE_CLOUD_QUOTA_PROJECT", None)
    environment.update(OPENCLASS_AGENT_KIND="tutor", MCP_SCOPE_PUBLIC_KEY="startup-test-public-key-placeholder", GEMINI_API_KEY="startup-test-placeholder")
    code = """import asyncio
from backend.runtime.server import app
async def check():
    async with app.router.lifespan_context(app):
        print('STARTUP_OK')
asyncio.run(check())
"""
    passed = []
    for label, omit_location in [("configured", False), ("missing_location", True)]:
        current = dict(environment)
        if omit_location:
            current.pop("GOOGLE_CLOUD_LOCATION", None)
        arguments = ["docker", "run", "--rm", "--network", "none"]
        for name, value in current.items():
            arguments += ["--env", name+"="+value]
        result = subprocess.run([*arguments, values["runtime_image"], "python", "-c", code], capture_output=True, text=True, timeout=45)
        ok = result.returncode == 0 and "STARTUP_OK" in result.stdout if not omit_location else result.returncode != 0 and "Configure GOOGLE_CLOUD_LOCATION" in result.stderr
        passed.append(ok)
        print(label+": "+("PASS" if ok else "FAIL"), flush=True)
    return all(passed)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
