"""OS / resource detection (Milestone 2 / Task 10).

Pure-Python parsers for the standard remote-probe outputs:
- /etc/os-release: distro ID, version, family, package manager
- uname -m: CPU architecture
- free -m: RAM and swap totals / available
- df -m /: root filesystem total and available
- dpkg -l / rpm -qa / pacman -Q: package-manager presence

The parsers are pure (no SSH / no subprocess). They take raw command
output as a string and return a structured :class:`HostInfo`. The
host detection flow runs the probes over SSH (or the local transport),
then feeds the captured stdout into these parsers.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field

# Map distro ID -> (os_family, package_manager).
_DISTRO_MAP: dict[str, tuple[str, str | None]] = {
    # Debian family
    "ubuntu": ("debian", "apt"),
    "debian": ("debian", "apt"),
    "linuxmint": ("debian", "apt"),
    "pop": ("debian", "apt"),
    "elementary": ("debian", "apt"),
    "kali": ("debian", "apt"),
    "raspbian": ("debian", "apt"),
    # RHEL family
    "rhel": ("rhel", "dnf"),
    "centos": ("rhel", "dnf"),
    "rocky": ("rhel", "dnf"),
    "almalinux": ("rhel", "dnf"),
    "fedora": ("rhel", "dnf"),
    "amazon": ("rhel", "dnf"),
    "ol": ("rhel", "dnf"),
    # SUSE family
    "sles": ("suse", "zypper"),
    "opensuse": ("suse", "zypper"),
    "suse": ("suse", "zypper"),
    # Alpine
    "alpine": ("alpine", "apk"),
    # Arch
    "arch": ("arch", "pacman"),
    "manjaro": ("arch", "pacman"),
    "endeavouros": ("arch", "pacman"),
    # FreeBSD / SmartOS
    "freebsd": ("freebsd", "pkg"),
}


@dataclass
class HostInfo:
    """Structured result of host detection."""

    os_family: str = "unknown"
    os_name: str = ""
    os_version: str = ""
    package_manager: str | None = None
    arch: str = "unknown"
    cpu_cores: int | None = None
    ram_total_mb: int | None = None
    ram_available_mb: int | None = None
    swap_total_mb: int | None = None
    disk_total_mb: int | None = None
    disk_available_mb: int | None = None
    raw: dict[str, str] = field(default_factory=dict)


_OS_RELEASE_LINE_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_os_release(text: str) -> HostInfo:
    """Parse the contents of ``/etc/os-release`` into a HostInfo."""
    info = HostInfo()
    info.raw["os_release"] = text
    distro_id = ""
    for raw_line in (text or "").splitlines():
        m = _OS_RELEASE_LINE_RE.match(raw_line.strip())
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        value = _strip_quotes(value)
        if key == "ID":
            info.os_name = value.lower()
            distro_id = info.os_name
        elif key == "VERSION_ID":
            info.os_version = value
    mapping = _DISTRO_MAP.get(distro_id)
    if mapping:
        info.os_family, info.package_manager = mapping
    return info


def parse_uname_m(text: str) -> str:
    """Return the CPU architecture from the output of ``uname -m``."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "unknown"
    return cleaned.split()[0] if cleaned else "unknown"


_FREE_MEM_RE = re.compile(
    r"^Mem:\s+(\d+)\s+(\d+)\s+(\d+)"
    r"(?:\s+(\d+))?(?:\s+(\d+))?(?:\s+(\d+))?",
    re.IGNORECASE,
)
_FREE_SWAP_RE = re.compile(r"^Swap:\s+(\d+)", re.IGNORECASE)


def parse_free_m(text: str) -> HostInfo:
    """Parse ``free -m`` output into the memory fields of a HostInfo."""
    info = HostInfo()
    info.raw["free"] = text
    for line in (text or "").splitlines():
        m_mem = _FREE_MEM_RE.match(line.strip())
        if m_mem:
            with contextlib.suppress(ValueError):
                info.ram_total_mb = int(m_mem.group(1))
                # 6th column is "available" if present, else fall back to free.
                avail = m_mem.group(6)
                if avail is not None:
                    info.ram_available_mb = int(avail)
                else:
                    info.ram_available_mb = int(m_mem.group(3))
            continue
        m_swap = _FREE_SWAP_RE.match(line.strip())
        if m_swap:
            with contextlib.suppress(ValueError):
                info.swap_total_mb = int(m_swap.group(1))
    return info


_DF_LINE_RE = re.compile(r"^(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+%\s+/$")


def parse_df(text: str) -> HostInfo:
    """Parse the output of ``df -m /`` into the disk fields of a HostInfo."""
    info = HostInfo()
    info.raw["df"] = text
    for line in (text or "").splitlines():
        m = _DF_LINE_RE.match(line.strip())
        if m:
            with contextlib.suppress(ValueError):
                info.disk_total_mb = int(m.group(2))
                info.disk_available_mb = int(m.group(4))
    return info


def parse_dpkg(text: str) -> bool:
    """Return True iff ``dpkg -l`` output contains at least one package."""
    if not text:
        return False
    return any(line.startswith("ii") for line in text.splitlines())


def parse_rpm(text: str) -> bool:
    """Return True iff ``rpm -qa`` output contains at least one package."""
    return bool((text or "").strip())


def parse_pacman(text: str) -> bool:
    """Return True iff ``pacman -Q`` output contains at least one package."""
    return bool((text or "").strip())


def detect_from_outputs(
    *,
    os_release: str = "",
    uname: str = "",
    free_m: str = "",
    df_m: str = "",
    dpkg_q: str = "",
    rpm_qa: str = "",
    pacman_q: str = "",
) -> HostInfo:
    """Combine the parsers above into a single HostInfo."""
    info = parse_os_release(os_release)
    info.arch = parse_uname_m(uname)
    mem = parse_free_m(free_m)
    info.ram_total_mb = mem.ram_total_mb
    info.ram_available_mb = mem.ram_available_mb
    info.swap_total_mb = mem.swap_total_mb
    disk = parse_df(df_m)
    info.disk_total_mb = disk.disk_total_mb
    info.disk_available_mb = disk.disk_available_mb

    # Package manager fallback: trust the os-release map first; if
    # absent, infer from a successful probe of a manager.
    if not info.package_manager:
        if parse_dpkg(dpkg_q):
            info.package_manager = "apt"
            info.os_family = info.os_family or "debian"
        elif parse_rpm(rpm_qa):
            info.package_manager = "dnf"
            info.os_family = info.os_family or "rhel"
        elif parse_pacman(pacman_q):
            info.package_manager = "pacman"
            info.os_family = info.os_family or "arch"
    return info


__all__ = [
    "HostInfo",
    "detect_from_outputs",
    "parse_df",
    "parse_dpkg",
    "parse_free_m",
    "parse_os_release",
    "parse_pacman",
    "parse_rpm",
    "parse_uname_m",
]
