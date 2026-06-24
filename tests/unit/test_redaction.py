"""Unit tests for the redaction engine (Milestone 0 / Task 4).

The redaction engine must:

- Strip known secret values (explicitly registered).
- Match common credential patterns (Bearer tokens, GitHub PATs, AWS keys,
  PEM private keys, basic auth in URLs).
- Preserve ordinary log content (free-form text, paths, IPs, normal
  English) -- no over-redaction of mundane text.
- Be idempotent: running it twice produces the same output as once.
- Never echo the registered secret back in its output.
"""

from __future__ import annotations

from vman.security.redaction import (
    Redactor,
    default_redactor,
    redact_line,
    redact_lines,
)

# --- Known-value redaction --------------------------------------------------


def test_redacts_known_exact_value() -> None:
    r = Redactor()
    r.register("hunter2")
    out = r.redact("login password hunter2 success")
    assert "hunter2" not in out
    assert "success" in out  # surrounding context preserved


def test_redaction_is_case_sensitive_by_default() -> None:
    r = Redactor()
    r.register("hunter2")
    # Case-insensitive would over-match; default must NOT treat
    # HUNTER2 the same as hunter2 unless asked.
    out = r.redact("HUNTER2 visible")
    assert "HUNTER2" in out


def test_registering_long_value_does_not_match_shorter_substring() -> None:
    r = Redactor()
    r.register("abcdEFGH1234567890XYZ")
    out = r.redact("here is a sentence with abcd short ref")
    assert "abcd" in out


def test_redact_multiple_secrets_in_one_line() -> None:
    r = Redactor()
    r.register("secret-A")
    r.register("secret-B")
    out = r.redact("alpha secret-A beta secret-B gamma")
    assert "secret-A" not in out
    assert "secret-B" not in out
    assert "alpha" in out and "beta" in out and "gamma" in out


def test_redact_does_not_echo_registered_value_in_its_output() -> None:
    r = Redactor()
    sentinel = "TMPL-secret-do-not-leak-12345"
    r.register(sentinel)
    out = r.redact(f"log line with {sentinel} embedded")
    assert sentinel not in out
    assert "REDACTED" in out


# --- Pattern-based redaction ------------------------------------------------


def test_redacts_bearer_token() -> None:
    line = "Authorization: Bearer abc.def.ghi"
    out = default_redactor().redact(line)
    assert "abc.def.ghi" not in out


def test_redacts_github_personal_access_token() -> None:
    # Build the PAT value at runtime so the file source never contains a
    # literal that resembles a real token.
    prefix = "ghp_"
    pat_body = "a" * 36
    pat = prefix + pat_body
    line = f"export GH_TOKEN={pat}"
    out = default_redactor().redact(line)
    assert pat not in out
    assert "REDACTED" in out


def test_redacts_aws_access_key_id() -> None:
    # 16 chars after AKIA per AWS access key id format.
    suffix_a = "ABCDEFGH"
    suffix_b = "IJKLMNOP"
    line = f"AWS_ACCESS_KEY_ID=AKIA{suffix_a}{suffix_b}"
    out = default_redactor().redact(line)
    assert f"AKIA{suffix_a}{suffix_b}" not in out


def test_redacts_basic_auth_in_url() -> None:
    line = "fetching https://user:supersecret@example.com/data"
    out = default_redactor().redact(line)
    assert "supersecret" not in out
    assert "example.com" in out  # host preserved


def test_redacts_pem_private_key_block() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nsomebase64content\n-----END RSA PRIVATE KEY-----\n"
    out = default_redactor().redact(pem)
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert "somebase64content" not in out


def test_redacts_openssh_private_key_marker() -> None:
    block = "-----BEGIN OPENSSH PRIVATE KEY-----\nxyz\n-----END OPENSSH PRIVATE KEY-----\n"
    out = default_redactor().redact(block)
    assert "BEGIN OPENSSH PRIVATE KEY" not in out
    assert "xyz" not in out


def test_redacts_key_value_pair_with_password_keyword() -> None:
    out = default_redactor().redact("db_password=verylongdatabasepasswordvalue12345")
    assert "verylongdatabasepasswordvalue12345" not in out
    assert "db_password=" in out  # the key name is preserved


# --- Over-redaction guards --------------------------------------------------


def test_preserves_normal_log_content() -> None:
    samples = [
        "INFO started worker pid=1234",
        "GET /api/health 200 in 3ms",
        "host=sg-1gb-01 os=ubuntu version=22.04",
        "free -m: total=1985 used=512 free=200",
        "no secrets here at all",
        "192.168.1.1 connected",
    ]
    redactor = default_redactor()
    for s in samples:
        assert redactor.redact(s) == s, f"over-redacted: {s!r}"


def test_redact_does_not_redact_short_common_words() -> None:
    r = default_redactor()
    for text in [
        "the cat sat on the mat",
        "user logged in successfully",
        "service restarted",
        "Configuration loaded",
        "value=42",
    ]:
        assert r.redact(text) == text


# --- Helpers ----------------------------------------------------------------


def test_redact_idempotent() -> None:
    r = Redactor()
    r.register("topsecret")
    once = r.redact("line with topsecret in it")
    twice = r.redact(once)
    assert once == twice


def test_redact_lines_helper() -> None:
    r = Redactor()
    r.register("pw1")
    lines = [
        "INFO starting",
        "DEBUG login attempt pw1 from 10.0.0.1",
        "INFO done",
    ]
    out = redact_lines(r, lines)
    assert "pw1" not in out[1]
    assert out[0] == "INFO starting"
    assert out[2] == "INFO done"


def test_redact_line_module_helper() -> None:
    long_token = "t" * 40
    line = f"config token={long_token}"
    out = redact_line(line)
    assert long_token not in out


def test_redactor_handles_empty() -> None:
    r = default_redactor()
    assert r.redact("") == ""
    # Empty register list does not error.
    Redactor().redact("anything")


def test_registration_with_empty_or_whitespace_does_nothing() -> None:
    r = Redactor()
    r.register("")
    r.register("   ")
    assert r.redact("hello world") == "hello world"


def test_registered_secrets_with_regex_metachars_are_escaped() -> None:
    r = Redactor()
    r.register("a.b+c*d")
    out = r.redact("literal a.b+c*d vs regex aXYZbZcZd")
    assert "a.b+c*d" not in out  # the literal value is redacted
    # The regex-shaped "aXYZbZcZd" must NOT be touched.
    assert "aXYZbZcZd" in out


def test_default_redactor_is_safe_to_share() -> None:
    a = default_redactor()
    b = default_redactor()
    assert a is b  # process-wide singleton, no per-call cost


def test_redact_large_input_does_not_break() -> None:
    r = default_redactor()
    big = "INFO line\n" * 100_000
    out = r.redact(big)
    assert isinstance(out, str)
    assert len(out) >= len(big)
