"""Manually probe ONLY the fixed read-only detector; never a research launcher.

Credentials are obtained in memory from the user's existing Git credential
manager, sent only to api.github.com via HTTPS, and never printed or saved.
Redirects are disabled. No arbitrary URL, workflow name, branch or payload.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
BASE = "https://api.github.com/repos/YBEMR/paper"
WORKFLOW = "agent-loop-watch.yml"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["inspect", "dispatch"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    allowed = ROOT / "research" / "agent_loop" / "validation"
    if not output.is_relative_to(allowed):
        raise SystemExit("probe output must be in agent_loop/validation")
    result = {"schema_version": 1, "operation": args.operation,
              "repository": "YBEMR/paper", "workflow": WORKFLOW,
              "detector_only": True, "research_calls": 0,
              "matlab_invoked": False, "requests": []}
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    token = None
    try:
        cred = subprocess.run(["git", "credential", "fill"],
                              input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, timeout=30, env=env)
        if cred.returncode:
            raise RuntimeError("existing Git credential manager unavailable")
        fields = dict(line.split("=", 1) for line in cred.stdout.splitlines() if "=" in line)
        token = fields.get("password")
        if not token:
            raise RuntimeError("no existing credential returned")
        opener = urllib.request.build_opener(NoRedirect())

        def api(path, method="GET", body=None):
            # All paths below are constants; redirects cannot carry credentials.
            headers = {"Authorization": "Bearer " + token,
                       "Accept": "application/vnd.github+json",
                       "X-GitHub-Api-Version": "2022-11-28",
                       "User-Agent": "YBEMR-paper-detector-probe"}
            raw = None if body is None else json.dumps(body).encode("utf-8")
            request = urllib.request.Request(BASE + path, data=raw, method=method, headers=headers)
            try:
                with opener.open(request, timeout=30) as response:
                    payload = response.read()
                    result["requests"].append({"path": path, "method": method,
                                               "http_status": response.status})
                    return json.loads(payload) if payload else None
            except urllib.error.HTTPError as exc:
                result["requests"].append({"path": path, "method": method,
                                           "http_status": exc.code})
                # Do not serialize response headers or body (may include secrets).
                raise RuntimeError("GitHub endpoint returned HTTP " + str(exc.code)) from None

        if args.operation == "dispatch":
            blob = api("/contents/.github/workflows/" + WORKFLOW + "?ref=main")
            remote = base64.b64decode(blob["content"], validate=False)
            local = ROOT / ".github" / "workflows" / WORKFLOW
            if remote != local.read_bytes():
                raise RuntimeError("published detector differs from locally inspected workflow")
            result["workflow_sha256"] = hashlib.sha256(remote).hexdigest()
            api("/actions/workflows/" + WORKFLOW + "/dispatches", "POST", {"ref": "main"})
            result["dispatch_accepted"] = True
        runs = api("/actions/runs?per_page=20")
        result["runs"] = [{key: run.get(key) for key in (
            "id", "name", "path", "event", "status", "conclusion", "html_url", "head_sha", "created_at")}
            for run in runs["workflow_runs"] if run.get("path") == ".github/workflows/" + WORKFLOW]
        result["probe_status"] = "COMPLETED"
    except Exception as exc:
        # Known exceptions carry no credentials. Arbitrary messages are suppressed.
        result["probe_status"] = "BLOCKED"
        result["error_type"] = type(exc).__name__
        result["reason"] = str(exc) if isinstance(exc, RuntimeError) else "probe unavailable; no credential details saved"
    finally:
        token = None
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["probe_status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
