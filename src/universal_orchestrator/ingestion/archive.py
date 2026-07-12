from __future__ import annotations

import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from universal_orchestrator.ingestion.hardening import IngestionLimits


@dataclass
class ArchiveExtractionReport:
    destination: str
    extracted_files: list[str] = field(default_factory=list)
    rejected_members: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_bytes: int = 0


def safe_extract_archive(
    archive_path: Path | str,
    destination: Path | str,
    limits: IngestionLimits | None = None,
) -> ArchiveExtractionReport:
    """Extract regular archive files without following paths or links."""

    source = Path(archive_path)
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    limits = limits or IngestionLimits()
    report = ArchiveExtractionReport(destination=str(root))
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > limits.max_archive_entries:
                report.warnings.append("Archive extraction skipped: entry limit exceeded.")
                return report
            for info in infos:
                if info.is_dir():
                    continue
                if _unsafe_member(info.filename) or _zip_is_link(info):
                    report.rejected_members.append(info.filename)
                    continue
                if report.total_bytes + info.file_size > limits.max_archive_uncompressed_bytes:
                    report.warnings.append("Archive extraction stopped at uncompressed-size limit.")
                    break
                target = _safe_target(root, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as incoming, target.open("wb") as outgoing:
                    _copy_bounded(incoming, outgoing, info.file_size, limits.max_archive_uncompressed_bytes - report.total_bytes)
                report.total_bytes += info.file_size
                report.extracted_files.append(str(target.relative_to(root)))
        return report
    if tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            members = archive.getmembers()
            if len(members) > limits.max_archive_entries:
                report.warnings.append("Archive extraction skipped: entry limit exceeded.")
                return report
            for member in members:
                if not member.isfile() or _unsafe_member(member.name) or member.issym() or member.islnk():
                    if member.name:
                        report.rejected_members.append(member.name)
                    continue
                if report.total_bytes + member.size > limits.max_archive_uncompressed_bytes:
                    report.warnings.append("Archive extraction stopped at uncompressed-size limit.")
                    break
                member_stream = archive.extractfile(member)
                if member_stream is None:
                    report.rejected_members.append(member.name)
                    continue
                target = _safe_target(root, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with member_stream, target.open("wb") as outgoing:
                    _copy_bounded(member_stream, outgoing, member.size, limits.max_archive_uncompressed_bytes - report.total_bytes)
                report.total_bytes += member.size
                report.extracted_files.append(str(target.relative_to(root)))
        return report
    report.warnings.append("Archive type is not supported for safe extraction.")
    return report


def _unsafe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return path.is_absolute() or ".." in path.parts or "\x00" in name


def _safe_target(root: Path, name: str) -> Path:
    target = (root / PurePosixPath(name)).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise ValueError(f"Archive member escapes extraction root: {name}")
    return target


def _zip_is_link(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _copy_bounded(incoming: object, outgoing: object, expected: int, remaining: int) -> None:
    reader = incoming
    writer = outgoing
    copied = 0
    while copied < expected:
        chunk = reader.read(min(1024 * 1024, expected - copied))  # type: ignore[attr-defined]
        if not chunk:
            break
        if copied + len(chunk) > remaining:
            raise ValueError("Archive member exceeded extraction limit.")
        writer.write(chunk)  # type: ignore[attr-defined]
        copied += len(chunk)
