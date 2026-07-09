from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


AUTHORITY_ORDER = {
    "runtime": 0,
    "user": 1,
    "product_contract": 2,
    "local_project": 3,
    "source": 4,
    "web": 5,
    "model": 6,
}


class SecurityPolicy:
    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def is_path_inside_workspace(self, path: Path | str) -> bool:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return False
        return True

    def is_archive_member_safe(self, name: str) -> bool:
        member = Path(name)
        return not member.is_absolute() and ".." not in member.parts

    def is_url_allowed(self, url: str, allow_internet: bool, allowed_hosts: set[str] | None = None) -> bool:
        if not allow_internet:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        if allowed_hosts and parsed.hostname not in allowed_hosts:
            return False
        return True

    def can_lower_authority_override(self, lower: str, higher: str) -> bool:
        return AUTHORITY_ORDER.get(lower, 99) <= AUTHORITY_ORDER.get(higher, 99)

