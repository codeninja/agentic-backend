"""Tests for the shared SSRF protection utility."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ninja_core.security import SSRFError, check_ssrf


class TestCheckSSRFDirectIPs:
    """Test blocking of direct IP addresses in private/reserved ranges."""

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.1.100",
        ],
    )
    def test_blocks_rfc1918_private_ranges(self, ip: str) -> None:
        result = check_ssrf(f"postgresql://{ip}:5432/db")
        assert result is not None
        assert "private/reserved range" in result

    @pytest.mark.parametrize("ip", ["127.0.0.1", "127.0.0.2", "127.255.255.255"])
    def test_blocks_loopback(self, ip: str) -> None:
        result = check_ssrf(f"http://{ip}:8080/api")
        assert result is not None
        assert "private/reserved range" in result

    @pytest.mark.parametrize("ip", ["169.254.0.1", "169.254.169.254"])
    def test_blocks_link_local_and_cloud_metadata(self, ip: str) -> None:
        result = check_ssrf(f"http://{ip}/latest/meta-data/")
        assert result is not None
        assert "private/reserved range" in result

    def test_blocks_zero_address(self) -> None:
        result = check_ssrf("http://0.0.0.0:8080/")
        assert result is not None

    @pytest.mark.parametrize("ip", ["::1", "fc00::1", "fe80::1"])
    def test_blocks_ipv6_private(self, ip: str) -> None:
        result = check_ssrf(f"http://[{ip}]:8080/")
        assert result is not None

    def test_allows_public_ip(self) -> None:
        result = check_ssrf("postgresql://8.8.8.8:5432/db")
        assert result is None

    def test_allows_public_ip_203(self) -> None:
        result = check_ssrf("http://203.0.113.1:8080/api")
        assert result is None


class TestCheckSSRFHostnames:
    """Test blocking of well-known metadata hostnames."""

    def test_blocks_google_metadata(self) -> None:
        result = check_ssrf("http://metadata.google.internal/computeMetadata/v1/")
        assert result is not None
        assert "cloud metadata" in result

    def test_blocks_metadata_internal(self) -> None:
        result = check_ssrf("http://metadata.internal/latest/")
        assert result is not None
        assert "cloud metadata" in result

    def test_blocks_metadata_case_insensitive(self) -> None:
        result = check_ssrf("http://METADATA.GOOGLE.INTERNAL/v1/")
        assert result is not None

    @patch("ninja_core.security.socket.getaddrinfo")
    def test_blocks_hostname_resolving_to_private_ip(self, mock_getaddrinfo) -> None:
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("10.0.0.5", 5432)),
        ]
        result = check_ssrf("postgresql://internal-db.example.com:5432/db")
        assert result is not None
        assert "10.0.0.5" in result

    @patch("ninja_core.security.socket.getaddrinfo")
    def test_allows_hostname_resolving_to_public_ip(self, mock_getaddrinfo) -> None:
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 5432)),
        ]
        result = check_ssrf("postgresql://db.example.com:5432/mydb")
        assert result is None

    @patch("ninja_core.security.socket.getaddrinfo", side_effect=OSError("DNS failure"))
    def test_allows_unresolvable_hostname(self, mock_getaddrinfo) -> None:
        """Unresolvable hostnames pass through — the connection itself will fail."""
        result = check_ssrf("postgresql://unknown-host.example.com:5432/db")
        assert result is None


class TestCheckSSRFEdgeCases:
    """Test edge cases and the allow_private_hosts override."""

    def test_allow_private_hosts_skips_all_checks(self) -> None:
        result = check_ssrf("http://169.254.169.254/latest/", allow_private_hosts=True)
        assert result is None

    def test_allow_private_hosts_for_localhost(self) -> None:
        result = check_ssrf("postgresql://127.0.0.1:5432/db", allow_private_hosts=True)
        assert result is None

    def test_no_hostname_passes_through(self) -> None:
        """URLs without a hostname (e.g. sqlite) should pass through."""
        result = check_ssrf("sqlite:///:memory:")
        assert result is None

    def test_empty_url_passes_through(self) -> None:
        result = check_ssrf("")
        assert result is None

    def test_error_message_includes_override_hint(self) -> None:
        result = check_ssrf("http://10.0.0.1:8080/")
        assert result is not None
        assert "--allow-private-hosts" in result


class TestSSRFError:
    """Test the SSRFError exception class."""

    def test_is_value_error(self) -> None:
        assert issubclass(SSRFError, ValueError)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(SSRFError, match="blocked"):
            raise SSRFError("Connection blocked")
