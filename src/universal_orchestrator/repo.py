from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import RepoMap
from universal_orchestrator.utils import iter_files


IGNORED_REPO_NAMES = {
    ".git",
    ".uo",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".md": "Markdown",
}


class RepoAnalyzer:
    def analyze(self, root: Path | str, max_files: int = 1000) -> RepoMap:
        path = Path(root).resolve()
        files = iter_files(path, IGNORED_REPO_NAMES, max_files)
        languages: dict[str, int] = {}
        package_files: list[str] = []
        hot_files: list[str] = []
        for file_path in files:
            suffix = file_path.suffix.lower()
            language = LANGUAGE_BY_SUFFIX.get(suffix)
            if language:
                languages[language] = languages.get(language, 0) + 1
            name = file_path.name
            rel = str(file_path.relative_to(path))
            if name in {
                "pyproject.toml",
                "package.json",
                "pnpm-lock.yaml",
                "requirements.txt",
                "Cargo.toml",
                "go.mod",
                "pytest.ini",
                "tox.ini",
            }:
                package_files.append(rel)
            if name in {"README.md", "pyproject.toml"} or rel.startswith("src/") or rel.startswith("tests/"):
                hot_files.append(rel)
        frameworks = self._frameworks(path, package_files, languages)
        return RepoMap(
            root=str(path),
            frameworks=frameworks,
            languages=dict(sorted(languages.items())),
            test_commands=self._test_commands(path, package_files),
            package_files=sorted(package_files),
            hot_files=sorted(hot_files)[:50],
            generated_or_dependency_dirs=sorted(name for name in IGNORED_REPO_NAMES if (path / name).exists()),
        )

    def _frameworks(self, root: Path, package_files: list[str], languages: dict[str, int]) -> list[str]:
        frameworks: list[str] = []
        if "pyproject.toml" in package_files or "Python" in languages:
            frameworks.append("python")
        if "package.json" in package_files:
            text = (root / "package.json").read_text(errors="replace")
            if "react" in text.lower():
                frameworks.append("react")
            frameworks.append("node")
        if "Cargo.toml" in package_files:
            frameworks.append("rust")
        return sorted(set(frameworks))

    def _test_commands(self, root: Path, package_files: list[str]) -> list[str]:
        commands: list[str] = []
        if "pyproject.toml" in package_files or (root / "tests").exists():
            commands.append("PYTHONPATH=src python -m unittest discover -s tests")
        if "package.json" in package_files:
            commands.append("npm test")
        if "Cargo.toml" in package_files:
            commands.append("cargo test")
        return commands
