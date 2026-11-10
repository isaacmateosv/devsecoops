"""Isolation configuration is ENFORCED, not assumed (Prompt 1 acceptance gate).

Runs canary commands inside the SAME hardened configuration the runner uses
(runner.hardening_flags) and asserts the restrictions actually hold at runtime.
"""
import subprocess

import pytest

import config
import runner
from conftest import requires_docker

IMAGE = config.RUNNER_IMAGE


def _canary(cmd: list[str]) -> subprocess.CompletedProcess:
    argv = ["docker", "run"] + runner.hardening_flags() + [IMAGE] + cmd
    return subprocess.run(argv, capture_output=True, text=True, timeout=30)


def test_config_contains_core_restrictions():
    flags = runner.hardening_flags()
    joined = " ".join(flags)
    assert "--network" in flags and "none" in flags
    assert "--read-only" in flags
    assert "--cap-drop" in flags and "ALL" in flags
    assert "no-new-privileges" in joined
    assert "65534:65534" in flags


@requires_docker
def test_network_is_denied():
    # With --network none there is no veth to any bridge (no eth0) and no
    # routing table entries -- so no outbound reachability. (The kernel still
    # instantiates empty tunnel-device templates like gre0/sit0 per netns;
    # those carry no connectivity and are ignored.)
    ifaces = set(_canary(["ls", "/sys/class/net"]).stdout.split())
    assert "eth0" not in ifaces, f"an attached network interface is present: {ifaces}"

    # /proc/net/route: header line + one line per route. --network none -> none.
    route = _canary(["cat", "/proc/net/route"]).stdout.strip().splitlines()
    data_lines = [l for l in route[1:] if l.strip()]
    assert data_lines == [], f"unexpected routes present (network reachable): {data_lines}"


@requires_docker
def test_runs_as_nonroot():
    p = _canary(["id", "-u"])
    assert p.stdout.strip() == "65534", p.stdout


@requires_docker
def test_root_filesystem_is_read_only():
    p = _canary(["touch", "/root/escape"])
    assert p.returncode != 0, "root fs was writable but should be read-only"


@requires_docker
def test_tmpfs_scratch_is_writable():
    p = _canary(["sh", "-c", "touch /tmp/ok && echo WROTE"])
    assert "WROTE" in p.stdout, p.stderr
