"""Unit tests for OS / resource detection (Milestone 2 / Task 10)."""

from __future__ import annotations

from vman.services.os_detection import (
    detect_from_outputs,
    parse_df,
    parse_dpkg,
    parse_free_m,
    parse_os_release,
    parse_pacman,
    parse_rpm,
    parse_uname_m,
)

# /etc/os-release parser


def test_parse_os_release_ubuntu() -> None:
    sample = (
        'NAME="Ubuntu"'
        + chr(10)
        + 'VERSION="22.04.3 LTS (Jammy Jellyfish)"'
        + chr(10)
        + "ID=ubuntu"
        + chr(10)
        + 'VERSION_ID="22.04"'
        + chr(10)
        + 'PRETTY_NAME="Ubuntu 22.04.3 LTS"'  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "debian"
    assert info.os_name == "ubuntu"
    assert info.os_version == "22.04"
    assert info.package_manager == "apt"


def test_parse_os_release_debian() -> None:
    sample = (
        'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"'
        + chr(10)
        + 'NAME="Debian GNU/Linux"'
        + chr(10)
        + 'VERSION_ID="12"'
        + chr(10)
        + "ID=debian"  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "debian"
    assert info.os_name == "debian"
    assert info.os_version == "12"
    assert info.package_manager == "apt"


def test_parse_os_release_rhel_family() -> None:
    sample = (
        'NAME="Rocky Linux"'
        + chr(10)
        + 'ID="rocky"'
        + chr(10)
        + 'VERSION_ID="9.3"'
        + chr(10)
        + 'PRETTY_NAME="Rocky Linux 9.3"'  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "rhel"
    assert info.package_manager == "dnf"


def test_parse_os_release_fedora_uses_dnf() -> None:
    sample = (
        'NAME="Fedora Linux"' + chr(10) + "ID=fedora" + chr(10) + "VERSION_ID=40"  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "rhel"
    assert info.package_manager == "dnf"


def test_parse_os_release_alpine() -> None:
    sample = (
        'NAME="Alpine Linux"' + chr(10) + "ID=alpine" + chr(10) + "VERSION_ID=3.19.0"  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "alpine"
    assert info.package_manager == "apk"


def test_parse_os_release_arch() -> None:
    sample = (
        'NAME="Arch Linux"'
        + chr(10)
        + "ID=arch"
        + chr(10)
        + 'PRETTY_NAME="Arch Linux"'  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_family == "arch"
    assert info.package_manager == "pacman"


def test_parse_os_release_quoted_values() -> None:
    sample = (
        "ID=ubuntu" + chr(10) + "VERSION_ID=22.04"  # end sample
    )
    info = parse_os_release(sample)
    assert info.os_name == "ubuntu"
    assert info.os_version == "22.04"


def test_parse_os_release_unknown_id_returns_unknown_family() -> None:
    sample = "ID=some-custom-distro" + chr(10)
    info = parse_os_release(sample)
    assert info.os_family == "unknown"
    assert info.package_manager is None


def test_parse_os_release_handles_empty_input() -> None:
    info = parse_os_release("")
    assert info.os_family == "unknown"
    assert info.os_name == ""


# uname -m


def test_parse_uname_x86_64() -> None:
    assert parse_uname_m("x86_64" + chr(10)) == "x86_64"


def test_parse_uname_aarch64() -> None:
    assert parse_uname_m("aarch64" + chr(10)) == "aarch64"


def test_parse_uname_armv7l() -> None:
    assert parse_uname_m("armv7l" + chr(10)) == "armv7l"


def test_parse_uname_strips_whitespace() -> None:
    assert parse_uname_m("  x86_64 " + chr(10)) == "x86_64"


def test_parse_uname_empty() -> None:
    assert parse_uname_m("") == "unknown"


# free -m


def test_parse_free_m_normal() -> None:
    sample = (
        "              total        used        free      shared  buff/cache   available"
        + chr(10)
        + "Mem:           1985         512         200"
        + "          10        1273        1300"
        + chr(10)
        + "Swap:          2047         100        1947"  # end sample
    )
    info = parse_free_m(sample)
    assert info.ram_total_mb == 1985
    assert info.ram_available_mb == 1300
    assert info.swap_total_mb == 2047


def test_parse_free_m_handles_kib_rows() -> None:
    sample = (
        "Mem:        2031616     524288     204800      10240     1302528    1331200"  # end sample
    )
    info = parse_free_m(sample)
    assert info.ram_total_mb is not None and info.ram_total_mb > 0


def test_parse_free_m_handles_empty() -> None:
    info = parse_free_m("")
    assert info.ram_total_mb is None


# df -m /


def test_parse_df_root_filesystem() -> None:
    sample = (
        "Filesystem     1M-blocks  Used Available Use% Mounted on"
        + chr(10)
        + "/dev/sda1           5000  1500      3500  30% /"  # end sample
    )
    info = parse_df(sample)
    assert info.disk_total_mb == 5000
    assert info.disk_available_mb == 3500


def test_parse_df_handles_overlay() -> None:
    sample = (
        "Filesystem     1M-blocks  Used Available Use% Mounted on"
        + chr(10)
        + "overlay         20000  5000     15000  25% /"  # end sample
    )
    info = parse_df(sample)
    assert info.disk_total_mb == 20000


def test_parse_df_empty() -> None:
    info = parse_df("")
    assert info.disk_total_mb is None


# dpkg / rpm / pacman


def test_parse_dpkg_present() -> None:
    sample = (
        "ii"
        + chr(9)
        + "bash"
        + chr(9)
        + "5.1"
        + chr(10)
        + "ii"
        + chr(9)
        + "curl"
        + chr(9)
        + "7.81"
        + chr(10)
    )
    assert parse_dpkg(sample) is True


def test_parse_dpkg_absent() -> None:
    assert parse_dpkg("") is False


def test_parse_rpm_present() -> None:
    sample = "curl-7.85.0-1.el9.x86_64" + chr(10) + "bash-5.1.8-1.el9.x86_64" + chr(10)
    assert parse_rpm(sample) is True


def test_parse_rpm_empty() -> None:
    assert parse_rpm("") is False


def test_parse_pacman_present() -> None:
    sample = "curl 7.85.0-1" + chr(10) + "bash 5.1.16-1" + chr(10)
    assert parse_pacman(sample) is True


# Combined detect_from_outputs


def test_detect_from_outputs_full_set() -> None:
    osr = "ID=ubuntu" + chr(10) + "VERSION_ID=22.04" + chr(10)
    un = "x86_64" + chr(10)
    fm = (
        "Mem:           1985         512         200"
        + chr(10)
        + "Swap:          2047         100        1947"
        + chr(10)
    )
    df = (
        "Filesystem     1M-blocks"
        + chr(10)
        + "/dev/sda1           5000  1500      3500  30% /"
        + chr(10)
    )
    dq = "ii" + chr(9) + "curl" + chr(9) + "7.81.0" + chr(10)
    out = detect_from_outputs(os_release=osr, uname=un, free_m=fm, df_m=df, dpkg_q=dq)
    assert out.os_family == "debian"
    assert out.os_name == "ubuntu"
    assert out.os_version == "22.04"
    assert out.arch == "x86_64"
    assert out.ram_total_mb == 1985
    assert out.disk_total_mb == 5000
    assert out.package_manager == "apt"


def test_detect_from_outputs_minimal() -> None:
    out = detect_from_outputs()
    assert out.os_family == "unknown"
    assert out.ram_total_mb is None
