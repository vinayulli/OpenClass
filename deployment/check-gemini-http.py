"""Direct Gemini diagnostic, without ADK or native dependency DLLs."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from dotenv import load_dotenv, dotenv_values
from gemini_diagnostics import describe_error, redact


def main():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    file_key = dotenv_values(env_path).get("GEMINI_API_KEY")
    if file_key and key != file_key:
        print("WARNING: The shell GEMINI_API_KEY overrides a different key in .env.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    if not model or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in model):
        raise ValueError("GEMINI_MODEL must be a Gemini model identifier")
    print(f"Direct HTTP probe: {model}; authentication: GEMINI_API_KEY", flush=True)
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": "Reply with exactly OPENCLASS_OK."}]}]}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            error.response_json = json.load(error)
        except (ValueError, UnicodeError):
            error.response_json = {}
        print(describe_error(error), file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"FAIL: network connection; {redact(error.reason)}", file=sys.stderr)
        return 1
    text = "".join(part.get("text", "") for candidate in result.get("candidates", []) for part in candidate.get("content", {}).get("parts", []))
    if "OPENCLASS_OK" not in text:
        print("Gemini accepted the request, but the expected response marker was absent.")
        return 1
    print("PASS: live Gemini request returned OPENCLASS_OK. ADK and database access are separate checks.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(describe_error(error), file=sys.stderr)
        sys.exit(1)
