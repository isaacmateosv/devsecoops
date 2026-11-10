"""Restricted execution runner.

Executes an untrusted artifact inside an ephemeral, hardened Docker container.
This is the project's safety boundary for the POC. Enforced restrictions:

  --network none                no network reachability
  --read-only                   immutable root filesystem
  --tmpfs /tmp (noexec,nosuid)  only writable scratch, cannot exec from it
  --user 65534:65534            runs as nobody, never root
  --cap-drop ALL                no Linux capabilities
  --security-opt no-new-privileges
  --memory / --memory-swap      capped RAM, swap disabled
  --cpus / --pids-limit         capped CPU and process count
  wall-clock timeout            hard kill of the container

The artifact and input are mounted read-only; only stdout/stderr/exit come back.
NOTE: Docker is a strong-but-not-absolute boundary. The blueprint calls for
VM-level isolation (gVisor/Kata/microVM) before accepting arbitrary hostile
uploads in production; that is recorded as a known limitation, not faked here.

Every execution returns a fully-populated, hashable ExecutionRecord so that any
downstream claim can cite real evidence.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import config
from contracts import ExecutionRecord, IsolationProfile


def _isolation_profile() -> IsolationProfile:
    return IsolationProfile(
        runner_image=config.RUNNER_IMAGE,
        memory_bytes=config.RUNNER_MEMORY_BYTES,
        cpus=config.RUNNER_CPUS,
        pids_limit=config.RUNNER_PIDS_LIMIT,
        wall_clock_timeout_s=config.RUNNER_TIMEOUT_S,
    )


def hardening_flags() -> list[str]:
    """The single source of truth for the restricted-execution configuration.
    Used by the real runner AND by the isolation test's canary, so they cannot
    drift apart."""
    return [
        "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", str(config.RUNNER_MEMORY_BYTES),
        "--memory-swap", str(config.RUNNER_MEMORY_BYTES),  # == memory -> no swap
        "--cpus", str(config.RUNNER_CPUS),
        "--pids-limit", str(config.RUNNER_PIDS_LIMIT),
    ]


def docker_run_argv(artifact_host_path: str, input_host_path: Optional[str],
                    image: Optional[str] = None) -> list[str]:
    """Build the hardened `docker run` command for an artifact execution."""
    image = image or config.RUNNER_IMAGE
    argv = ["docker", "run"] + hardening_flags()
    argv += ["-v", f"{artifact_host_path}:/art/program:ro"]
    if input_host_path:
        argv += ["-v", f"{input_host_path}:/in/input:ro"]
    argv += [image, "/art/program"]
    if input_host_path:
        argv += ["/in/input"]
    return argv


def run(artifact_id: str, artifact_sha256: str, artifact_host_path: str,
        input_host_path: Optional[str] = None, input_sha256: Optional[str] = None,
        argv_label: Optional[list[str]] = None) -> ExecutionRecord:
    exec_id = f"exec_{uuid.uuid4().hex[:12]}"
    profile = _isolation_profile()
    cmd = docker_run_argv(artifact_host_path, input_host_path)

    rec = ExecutionRecord(
        id=exec_id, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        input_sha256=input_sha256, argv=argv_label or ["/art/program"],
        isolation=profile,
    )

    t0 = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=config.RUNNER_TIMEOUT_S, stdin=subprocess.DEVNULL,
        )
        rec.exit_code = proc.returncode
        rec.stdout = proc.stdout
        rec.stderr = proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rec.stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        rec.stderr = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        rec.exit_code = None
        rec.status = "error"
    except Exception as e:  # docker not available, etc. -- recorded, never faked
        rec.status = "error"
        rec.stderr = f"runner error: {e}"

    rec.duration_ms = int((time.monotonic() - t0) * 1000)
    rec.timed_out = timed_out
    rec.stdout_sha256 = hashlib.sha256(rec.stdout.encode()).hexdigest()
    from contracts import utcnow
    rec.finished_at = utcnow()
    return rec
