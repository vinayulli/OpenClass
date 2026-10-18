"""Build and push images using stdin authentication; never exposes a credential."""
import json
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    import google.auth
    from google.auth.transport.requests import Request
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id="hackathon-506016")
    credentials.refresh(Request())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=["runtime", "data-mcp", "github-mcp", "web"])
    args = parser.parse_args()
    config = ROOT/".cache/deployment-docker"
    config.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "DOCKER_CONFIG": str(config)}
    registry = "us-central1-docker.pkg.dev"
    def run(arguments, **kwargs):
        return subprocess.run(["docker", *arguments], cwd=ROOT, env=environment, check=True, **kwargs)
    try:
        run(["login", "-u", "oauth2accesstoken", "--password-stdin", registry], input=credentials.token.encode())
        manifest = ROOT/"deployment/generated/images.json"
        images = json.loads(manifest.read_text()) if manifest.exists() else {}
        tag = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        for name, dockerfile in [("runtime", "backend/runtime/Dockerfile"), ("data-mcp", "mcp_servers/data/Dockerfile"), ("github-mcp", "mcp_servers/github/Dockerfile"), ("web", "Dockerfile")]:
            if args.only and name not in args.only:
                continue
            image = f"{registry}/hackathon-506016/openclass/{name}:{tag}"
            print("Building "+name, flush=True)
            build = ["build", "--platform", "linux/amd64", "--provenance=false", "-f", dockerfile, "-t", image]
            if name == "runtime":
                if images.get("runtime"):
                    # Reuse installed dependencies only when the base image's
                    # dependency declaration is byte-for-byte identical.
                    probe = run(["run", "--rm", "--network", "none", images["runtime"], "python", "-c", "import hashlib; print(hashlib.sha256(open('/app/pyproject.toml','rb').read()).hexdigest())"], capture_output=True, text=True)
                    if probe.stdout.strip() == hashlib.sha256((ROOT/"pyproject.toml").read_bytes()).hexdigest():
                        build += ["--build-arg", "OPENCLASS_RUNTIME_BASE="+images["runtime"], "--build-arg", "OPENCLASS_REUSE_DEPENDENCIES=true"]
                from google.auth.transport.requests import AuthorizedSession
                with AuthorizedSession(credentials) as session:
                    response = session.get("https://networkservices.googleapis.com/v1/projects/hackathon-506016/locations/us-central1/agentGateways/openclass-egress", timeout=30)
                    if not response.ok:
                        raise RuntimeError("Cannot retrieve Gateway trust certificates; HTTP "+str(response.status_code))
                    certificates = response.json().get("agentGatewayCard", {}).get("rootCertificates", [])
                    if not certificates or not all(isinstance(cert, str) and "-----BEGIN CERTIFICATE-----" in cert for cert in certificates):
                        raise RuntimeError("Gateway did not provide valid PEM root certificates")
                    environment["AGENT_GATEWAY_ROOT_CERTIFICATES"] = "\n".join(certificates)
                build += ["--build-arg", "AGENT_GATEWAY_ROOT_CERTIFICATES"]
            if name == "web":
                build += ["--build-arg", "OPENCLASS_RUNTIME_IMAGE="+images["runtime"]]
            run([*build, "."])
            credentials.refresh(Request())
            run(["login", "-u", "oauth2accesstoken", "--password-stdin", registry], input=credentials.token.encode())
            run(["push", image])
            images[name] = image
            (ROOT/"deployment/generated/images.json").write_text(json.dumps(images, indent=2)+"\n")
    finally:
        run(["logout", registry])


if __name__ == "__main__":
    main()
