from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SecurityPolicy:
    def is_url_allowed(self, url: str, allow_internet: bool, allowed_hosts: set[str] | None = None) -> bool:
        if not allow_internet:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        hostname = parsed.hostname.lower()
        normalized_allowlist = {host.lower() for host in allowed_hosts or set()}
        if allowed_hosts is not None:
            return hostname in normalized_allowlist
        try:
            addresses = {ipaddress.ip_address(hostname)}
        except ValueError:
            try:
                addresses = {
                    ipaddress.ip_address(item[4][0])
                    for item in socket.getaddrinfo(
                        hostname,
                        parsed.port or (443 if parsed.scheme == "https" else 80),
                        type=socket.SOCK_STREAM,
                    )
                }
            except (OSError, ValueError):
                return False
        return bool(addresses) and all(self._is_public_address(address) for address in addresses)

    def _is_public_address(self, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return not any(
            [
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            ]
        )
