"""Run Terraform in Docker with read-only ADC, without shell execution-policy changes."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    directory = (ROOT/sys.argv[1]).resolve()
    if not directory.is_relative_to(ROOT):
        raise SystemExit("Terraform directory must be inside OpenClass")
    adc = Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or str(Path(os.environ["APPDATA"])/"gcloud/application_default_credentials.json"))
    if not adc.is_file():
        raise SystemExit("Application Default Credentials are missing")
    result = subprocess.run(["docker", "run", "--rm", "--mount", f"type=bind,source={ROOT},target=/work", "--mount", f"type=bind,source={adc},target=/credentials/adc.json,readonly", "-e", "GOOGLE_APPLICATION_CREDENTIALS=/credentials/adc.json", "-e", "GOOGLE_CLOUD_QUOTA_PROJECT=hackathon-506016", "-w", "/work/"+directory.relative_to(ROOT).as_posix(), "hashicorp/terraform:1.13", *sys.argv[2:]])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
