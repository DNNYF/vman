"""Integration tests for the SSH runner (Milestone 2 / Task 9).

The runner is exercised through a fake transport (an in-process
``FakeTransport``) so the tests do not require a real SSH server.
That keeps the test suite fast and deterministic on any host.

Acceptance from the plan:
- strict host key checking
- captures stdout / stderr / exit code
- timeouts work
- credentials are redacted from logs
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from vman.security.host_keys import (
    HostKeyFingerprint,
    fingerprint_from_public_key_bytes,
)
from vman.security.redaction import default_redactor
from vman.services.ssh_runner import (
    CommandResult,
    HostKeyMismatchError,
    SshRunner,
    Transport,
)

# A "good" key/fingerprint pair used by default in these tests.
GOOD_KEY = b"ssh-ed25519-fake-server-public-key-bytes"
GOOD_FP = fingerprint_from_public_key_bytes("ssh-ed25519", GOOD_KEY)
OTHER_FP = fingerprint_from_public_key_bytes("ssh-ed25519", b"some-other-key-bytes")


class FakeTransport(Transport):
    """A scripted in-process transport for tests."""

    def __init__(
        self,
        *,
        script: list[CommandResult] | None = None,
        behaviour: Callable[[str], CommandResult] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._script = list(script or [])
        self._behaviour = behaviour
        self._delay = delay
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def connect(self, *, host: str, port: int, user: str) -> None:
        with self.lock:
            self.calls.append({"op": "connect", "host": host, "port": port, "user": user})

    def run(
        self,
        *,
        command: str,
        timeout: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        with self.lock:
            self.calls.append(
                {
                    "op": "run",
                    "command": command,
                    "timeout": timeout,
                    "env": dict(env or {}),
                }
            )
        if self._delay:
            time.sleep(self._delay)
        if self._behaviour is not None:
            return self._behaviour(command)
        if self._script:
            return self._script.pop(0)
        return CommandResult(stdout="", stderr="", exit_code=0)

    def disconnect(self) -> None:
        with self.lock:
            self.calls.append({"op": "disconnect"})

    def server_host_key(self) -> HostKeyFingerprint:
        return GOOD_FP


def _runner(
    transport: Transport,
    *,
    expected_fingerprint: HostKeyFingerprint | None = GOOD_FP,
) -> SshRunner:
    return SshRunner(
        transport=transport,
        host="example.com",
        port=22144,
        username="root",
        expected_fingerprint=expected_fingerprint,
        redactor=default_redactor(),
    )


def test_run_returns_stdout_stderr_exit_code() -> None:
    transport = FakeTransport(
        script=[
            CommandResult(stdout="hello", stderr="warn", exit_code=0),
        ]
    )
    runner = _runner(transport)
    result = runner.run("echo hello")
    assert result.stdout == "hello"
    assert result.stderr == "warn"
    assert result.exit_code == 0


def test_run_captures_nonzero_exit_code() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="boom", exit_code=2)])
    runner = _runner(transport)
    result = runner.run("false")
    assert result.exit_code == 2
    assert result.stderr == "boom"


def test_run_calls_transport_with_command_and_timeout() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="ok", stderr="", exit_code=0)])
    runner = _runner(transport)
    runner.run("ls -la", timeout=5.0)
    run_call = [c for c in transport.calls if c["op"] == "run"][0]
    assert run_call["command"] == "ls -la"
    assert run_call["timeout"] == 5.0


def test_run_passes_env() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="ok", stderr="", exit_code=0)])
    runner = _runner(transport)
    runner.run("deploy.sh", env={"DEPLOY_ENV": "prod"})
    run_call = [c for c in transport.calls if c["op"] == "run"][0]
    assert run_call["env"]["DEPLOY_ENV"] == "prod"


def test_run_raises_on_host_key_mismatch() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="", exit_code=0)])
    runner = SshRunner(
        transport=transport,
        host="example.com",
        port=22,
        username="root",
        expected_fingerprint=OTHER_FP,  # does NOT match transport's
        redactor=default_redactor(),
    )
    with pytest.raises(HostKeyMismatchError):
        runner.run("ls")


def test_run_succeeds_when_fingerprint_matches() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="ok", stderr="", exit_code=0)])
    runner = _runner(transport, expected_fingerprint=GOOD_FP)
    result = runner.run("ls")
    assert result.exit_code == 0


def test_run_skips_host_key_check_when_expected_fingerprint_is_none() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="ok", stderr="", exit_code=0)])
    runner = _runner(transport, expected_fingerprint=None)
    result = runner.run("ls")
    assert result.exit_code == 0


def test_run_redacts_secrets_in_command_output() -> None:
    """Even when the remote echoes back a secret we registered, the
    returned CommandResult MUST have it redacted."""
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="", exit_code=0)])
    runner = _runner(transport)
    runner.register_secret_for_redaction("topsecret-pw-12345")
    transport._behaviour = lambda cmd: CommandResult(
        stdout="hello topsecret-pw-12345 world",
        stderr="also topsecret-pw-12345",
        exit_code=0,
    )
    result = runner.run("echo hi")
    assert "topsecret-pw-12345" not in result.stdout
    assert "topsecret-pw-12345" not in result.stderr


def test_timeout_propagates_to_transport() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="", exit_code=0)])
    runner = _runner(transport)
    runner.run("sleep 999", timeout=2.5)
    run_call = [c for c in transport.calls if c["op"] == "run"][0]
    assert run_call["timeout"] == 2.5


def test_connect_called_before_run() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="", exit_code=0)])
    runner = _runner(transport)
    runner.run("ls")
    ops = [c["op"] for c in transport.calls]
    assert ops[0] == "connect"
    assert "run" in ops
    assert ops[-1] == "disconnect"


def test_disconnect_called_on_error() -> None:
    """Even when the command fails, the transport must be cleanly closed."""
    transport = FakeTransport(script=[CommandResult(stdout="", stderr="err", exit_code=99)])
    runner = _runner(transport)
    result = runner.run("false")
    assert result.exit_code == 99
    assert any(c["op"] == "disconnect" for c in transport.calls)


def test_runner_uses_provided_port_and_user() -> None:
    transport = FakeTransport(script=[CommandResult(stdout="ok", stderr="", exit_code=0)])
    runner = SshRunner(
        transport=transport,
        host="h",
        port=12345,
        username="deploy",
        expected_fingerprint=GOOD_FP,
        redactor=default_redactor(),
    )
    runner.run("ls")
    connect_call = [c for c in transport.calls if c["op"] == "connect"][0]
    assert connect_call["port"] == 12345
    assert connect_call["user"] == "deploy"


def test_runner_rejects_empty_command() -> None:
    transport = FakeTransport()
    runner = _runner(transport)
    with pytest.raises(ValueError):
        runner.run("")


def test_runner_redacts_stored_secret_in_subsequent_runs() -> None:
    transport = FakeTransport(
        script=[
            CommandResult(stdout="cred=topsecret-pw-12345 ok", stderr="", exit_code=0),
            CommandResult(stdout="done", stderr="", exit_code=0),
        ]
    )
    runner = _runner(transport)
    runner.register_secret_for_redaction("topsecret-pw-12345")
    a = runner.run("a")
    b = runner.run("b")
    assert "topsecret-pw-12345" not in a.stdout
    assert "topsecret-pw-12345" not in b.stdout
