#!/usr/bin/env python3
"""
Test Impact Analysis (TIA) — multi-language v3
===============================================
Supports: C# / .NET, Java (Maven + Gradle), Node.js (JS / TS)

Three layered strategies (all active in "hybrid" mode):
  1. Project dependency graph  — parse build files to find which test
                                 projects reference the changed source project
  2. Convention mapping        — FooService → FooServiceTests / FooService.test
  3. Symbol search             — extract public types from changed file,
                                 scan cached test files for references

Usage:
    python assess_impact.py --base HEAD~1 [--root DIR] [--lang dotnet|java|node]
    python assess_impact.py --base HEAD~1 --output json
    python assess_impact.py --unstaged
    python assess_impact.py --base HEAD~1 --run
    python assess_impact.py --base HEAD~1 --run -- --no-build
"""

from __future__ import annotations

__version__ = "1.2.0"

import abc
import argparse
import bisect
import collections
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FILTER_CLASS_LIMIT = 40

IGNORED_EXTENSIONS: Tuple[str, ...] = (
    ".md", ".txt", ".rst",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz",
    ".jks", ".keystore",           # Android signing keys
)

IGNORED_FILENAMES: Tuple[str, ...] = (
    ".gitignore", ".gitattributes", ".gitmodules",
    ".editorconfig",
    "license", "licence", "notice", "authors", "changelog",
    "local.properties",            # Android: machine-specific SDK paths
)

EXCLUDED_DIRS: Tuple[str, ...] = (
    "obj", "bin", ".vs",           # .NET
    "target", ".gradle", "build",  # Java / Gradle / Android
    "node_modules", "dist", ".next", ".nuxt", "coverage",  # Node
    ".git", ".idea", "packages", ".nuget",
)

# Node adapter uses this instead of EXCLUDED_DIRS so that npm workspace
# directories named "packages" are not silently skipped.
_NODE_EXCLUDED_DIRS: FrozenSet[str] = frozenset(
    EXCLUDED_DIRS
) - {"packages"}

_EXCLUDED_SET: FrozenSet[str] = frozenset(EXCLUDED_DIRS)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class FileStatus(str, Enum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"
    COPIED = "C"
    TYPE_CHANGED = "T"


class ChangeCategory(Enum):
    INFRA = auto()    # always run all tests
    IGNORED = auto()  # skip, no tests needed
    SOURCE = auto()   # full 3-strategy analysis
    CONFIG = auto()   # owning project's tests only
    UNKNOWN = auto()  # safe fallback: run all


@dataclass
class FileChange:
    path: str
    old_path: str
    status: FileStatus

    @property
    def is_deleted(self) -> bool:
        return self.status == FileStatus.DELETED

    @property
    def is_rename(self) -> bool:
        return self.status in (FileStatus.RENAMED, FileStatus.COPIED)

    def analysis_paths(self) -> List[str]:
        if self.is_rename:
            return [self.path, self.old_path]
        return [self.path]


@dataclass
class Project:
    name: str
    path: Path           # path to the project/build file
    is_test_project: bool = False
    project_references: List[str] = field(default_factory=list)
    # Resolved build-file paths of referenced projects (exact, no name
    # collisions). Used before project_references name matching.
    reference_paths: List[Path] = field(default_factory=list)
    group_id: str = ""   # Maven groupId for qualified artifact matching

    @property
    def directory(self) -> Path:
        return self.path.parent


@dataclass
class ImpactResult:
    changes: List[FileChange]
    affected_source_projects: List[str]
    affected_test_projects: List[str]
    affected_test_classes: Set[str]
    test_filter: str
    test_project_paths: List[str]
    workspace_files: List[str]
    run_all: bool
    reason: str
    language: str = "unknown"
    test_command: str = ""
    strategy_notes: List[str] = field(default_factory=list)

    @property
    def solution_paths(self) -> List[str]:
        """Backward-compatible alias for workspace_files."""
        return self.workspace_files


# ---------------------------------------------------------------------------
# Git analysis
# ---------------------------------------------------------------------------

def _run_git(*args: str, cwd: Optional[Path] = None) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git", *args], result.stdout, result.stderr
        )
    return result.stdout


def get_git_root(cwd: Path) -> Path:
    try:
        out = _run_git("rev-parse", "--show-toplevel", cwd=cwd)
        return Path(out.strip()).resolve()
    except subprocess.CalledProcessError:
        return cwd.resolve()


def _parse_name_status(out: str) -> List[FileChange]:
    changes: List[FileChange] = []
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status_char = parts[0][0].upper()
        try:
            status = FileStatus(status_char)
        except ValueError:
            continue
        if status in (FileStatus.RENAMED, FileStatus.COPIED) and len(parts) >= 3:
            changes.append(FileChange(
                path=parts[2].strip(), old_path=parts[1].strip(), status=status,
            ))
        else:
            p = parts[1].strip()
            changes.append(FileChange(path=p, old_path=p, status=status))
    return changes


_GIT_REF_RE = re.compile(r'^[A-Za-z0-9_./:@^~{}\[\]\\-]{1,250}$')


def _validate_ref(ref: str, name: str) -> str:
    if not _GIT_REF_RE.match(ref):
        print(f"[ERROR] Invalid git ref for {name}: {ref!r}", file=sys.stderr)
        sys.exit(1)
    return ref


def get_changed_files(
    base_ref: str, head_ref: str = "HEAD", git_root: Optional[Path] = None,
) -> List[FileChange]:
    try:
        out = _run_git(
            "diff", "--name-status", "--diff-filter=DACMRT",
            _validate_ref(base_ref, "--base"), _validate_ref(head_ref, "--head"),
            "--", cwd=git_root,
        )
        return _parse_name_status(out)
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] git diff failed: {exc.stderr.strip()}", file=sys.stderr)
        return []


def get_changed_files_working_tree(
    git_root: Optional[Path] = None, staged_only: bool = False,
) -> List[FileChange]:
    seen: Set[str] = set()
    all_changes: List[FileChange] = []
    extras = [["--cached"]] if staged_only else [["--cached"], []]
    for extra in extras:
        try:
            out = _run_git(
                "diff", "--name-status", "--diff-filter=DACMRT", *extra, cwd=git_root,
            )
            for change in _parse_name_status(out):
                if change.path not in seen:
                    seen.add(change.path)
                    all_changes.append(change)
        except subprocess.CalledProcessError:
            pass
    return all_changes


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def _in_hidden_dir(path: str) -> bool:
    """True when any directory segment is hidden (.claude, .github, .vscode,
    …) — tooling config that never affects test execution paths."""
    parts = path.replace("\\", "/").split("/")[:-1]
    return any(p.startswith(".") for p in parts)


def _iter_files(
    root: Path,
    *,
    filenames: Optional[FrozenSet[str]] = None,
    suffixes: Optional[Tuple[str, ...]] = None,
    excluded: FrozenSet[str] = _EXCLUDED_SET,
) -> Iterator[Path]:
    """Yield files under root matching lowercase filenames or suffixes,
    pruning excluded directories during the walk (unlike rglob, which
    descends into node_modules/obj/target before results can be filtered)."""
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excluded]
        for fname in files:
            low = fname.lower()
            if (filenames is not None and low in filenames) or (
                suffixes is not None and low.endswith(suffixes)
            ):
                yield Path(dirpath) / fname


def _find_owner(projects: List[Project], file_abs: Path) -> Optional[Project]:
    best: Optional[Project] = None
    best_len = 0
    for proj in projects:
        try:
            file_abs.relative_to(proj.directory)
            length = len(str(proj.directory))
            if length > best_len:
                best_len = length
                best = proj
        except ValueError:
            continue
    return best


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _find_by_name(projects: List[Project], name: str) -> List[Project]:
    """Return projects whose name or build-file stem matches (case-insensitive).
    A 'group:artifact' qualified name matches group_id + artifact when targets
    declare a group; falls back to artifact-only matching otherwise."""
    if ":" in name:
        group, _, artifact = name.partition(":")
        gl, al = group.lower(), artifact.lower()
        hits = [
            p for p in projects
            if (p.name.lower() == al or p.path.stem.lower() == al)
            and p.group_id and p.group_id.lower() == gl
        ]
        if hits:
            return hits
        name = artifact
    nl = name.lower()
    return [p for p in projects if p.name.lower() == nl or p.path.stem.lower() == nl]


def _ref_targets(
    proj: Project, projects: List[Project], by_path: Dict[Path, Project],
) -> List[Project]:
    """Resolve a project's references: exact path matches first, then names."""
    targets: List[Project] = []
    for ref_path in proj.reference_paths:
        target = by_path.get(ref_path)
        if target:
            targets.append(target)
    for ref_name in proj.project_references:
        targets.extend(_find_by_name(projects, ref_name))
    return targets


# ---------------------------------------------------------------------------
# Shared: dependency graph (language-agnostic)
# ---------------------------------------------------------------------------

def build_reverse_deps(projects: List[Project]) -> Dict[Path, Set[Path]]:
    """
    Return {source_project_path: set_of_test_project_paths}.
    BFS-transitive: if B depends on A, and TestB tests B, then A changing → TestB runs.
    """
    by_path: Dict[Path, Project] = {p.path: p for p in projects}

    direct: Dict[Path, Set[Path]] = {p.path: set() for p in projects}
    for proj in projects:
        if not proj.is_test_project:
            continue
        for ref_proj in _ref_targets(proj, projects, by_path):
            direct[ref_proj.path].add(proj.path)

    dependents: Dict[Path, Set[Path]] = {p.path: set() for p in projects}
    for proj in projects:
        for ref_proj in _ref_targets(proj, projects, by_path):
            dependents[ref_proj.path].add(proj.path)

    result: Dict[Path, Set[Path]] = {path: set(testers) for path, testers in direct.items()}
    for source_path in [p.path for p in projects]:
        visited: Set[Path] = {source_path}
        queue: collections.deque = collections.deque(dependents.get(source_path, set()))
        while queue:
            dep_path = queue.popleft()
            if dep_path in visited:
                continue
            visited.add(dep_path)
            result[source_path].update(direct.get(dep_path, set()))
            queue.extend(dependents.get(dep_path, set()) - visited)

    return result


def strategy_dependency_graph(
    file_path: str,
    projects: List[Project],
    reverse_deps: Dict[Path, Set[Path]],
    git_root: Path,
) -> Tuple[Optional[Project], Set[Path]]:
    file_abs = (git_root / file_path).resolve()
    owner = _find_owner(projects, file_abs)
    if not owner:
        return None, set()
    if owner.is_test_project:
        return owner, {owner.path} | reverse_deps.get(owner.path, set())
    return owner, reverse_deps.get(owner.path, set())


# ---------------------------------------------------------------------------
# Language adapter interface
# ---------------------------------------------------------------------------

class LanguageAdapter(abc.ABC):
    language: str = "unknown"

    # Build-file markers identifying this ecosystem. detect_adapters() scans
    # the tree once for all adapters' markers instead of one walk per adapter.
    marker_filenames: FrozenSet[str] = frozenset()
    marker_suffixes: Tuple[str, ...] = ()

    @abc.abstractmethod
    def detect(self, root: Path) -> bool:
        """Return True if this adapter handles the project at root."""

    @abc.abstractmethod
    def has_build_file(self, directory: Path) -> bool:
        """True if directory directly contains this ecosystem's build file.
        Used to route changed files to adapters in polyglot repos: the nearest
        ancestor directory with a build file owns the file."""

    @abc.abstractmethod
    def classify(self, change: FileChange) -> ChangeCategory:
        """Classify a single file change."""

    @abc.abstractmethod
    def discover(self, root: Path) -> Tuple[List[Project], List[Path]]:
        """Return (all_projects, workspace_root_files)."""

    @abc.abstractmethod
    def build_test_file_cache(self, test_projects: List[Project]) -> Dict[Path, str]:
        """Pre-load test source files into memory."""

    @abc.abstractmethod
    def strategy_convention(
        self, change: FileChange, test_projects: List[Project],
    ) -> List[Tuple[Path, str]]:
        """Map source→test by naming convention. Returns [(proj_path, test_id)]."""

    @abc.abstractmethod
    def strategy_symbol_search(
        self,
        change: FileChange,
        test_projects: List[Project],
        git_root: Path,
        cache: Dict[Path, str],
    ) -> List[Tuple[Path, str]]:
        """Find test files referencing public types from the changed file."""

    @abc.abstractmethod
    def build_filter(self, test_identifiers: Set[str]) -> Tuple[str, bool]:
        """Build a runner filter string. Returns (filter_str, was_capped)."""

    @abc.abstractmethod
    def run_tests(
        self, result: ImpactResult, extra_args: List[str], cwd: Optional[Path],
    ) -> int:
        """Execute the test suite. Returns exit code."""

    @abc.abstractmethod
    def fmt_command(self, result: ImpactResult) -> str:
        """Return the test command as a single-line string."""

    def is_test_file(self, path: str) -> bool:
        """True if path is a test file (not production source).
        DotNetAdapter overrides to True: .NET test projects contain only tests.
        Java/Node use path-based detection.
        """
        return False

    def extract_test_identifiers(self, file_path: Path, content: str) -> List[str]:
        """Extract test class names (or file stems for Node) from a test file."""
        return []

    def prefer_run_all_when_all_affected(self) -> bool:
        """True → use workspace root file when all test projects are affected.
        .NET uses .sln; Java uses mvn/gradlew root. Node prefers per-file
        --testPathPattern filtering even when fully affected.
        """
        return True

    def fill_missing_test_classes(
        self,
        affected_test_paths: Set[Path],
        affected_classes: Set[str],
        projects: List[Project],
    ) -> Set[str]:
        """For transitively-affected test projects with no specific class entry,
        optionally inject all their test IDs. Default: no-op."""
        return affected_classes

    # Set to a compiled regex in subclasses to enable method-level precision.
    # Must capture the method name in group 1.
    method_decl_re: Optional[re.Pattern] = None


# ---------------------------------------------------------------------------
# .NET adapter
# ---------------------------------------------------------------------------

_DOTNET_TEST_PACKAGES: Set[str] = {
    "xunit", "xunit.core", "xunit.runner.visualstudio",
    "nunit", "nunit3testadapter",
    "mstest.testframework", "mstest.testadapter",
    "microsoft.net.test.sdk",
    "moq", "nsubstitute", "fluentassertions",
    "specflow", "bunit", "shouldly",
    "autofixture", "bogus",
    "coverlet.collector", "coverlet.msbuild",
}

_DOTNET_TEST_SUFFIXES: Tuple[str, ...] = (
    ".tests", ".test", ".specs", ".spec",
    "tests", "test", "specs", "spec",
)

_DOTNET_SLN_RE = re.compile(
    r'Project\("[^"]*"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+\.csproj)"',
    re.IGNORECASE,
)

_DOTNET_TYPE_DECL_RE = re.compile(
    r'\b(?:public|internal)\s+'
    r'(?:(?:abstract|sealed|static|partial|readonly|new)\s+)*'
    r'(?:class|interface|enum|struct|record)\s+(\w+)',
)

_DOTNET_TEST_CLASS_RE = re.compile(r'\bclass\s+(\w+)')

# Matches C# method/constructor declarations that start with at least one access modifier.
# Captures the method name (last identifier before the opening parenthesis).
_DOTNET_METHOD_RE = re.compile(
    r'^\s*'
    r'(?:(?:public|protected|internal|private|static|virtual|override|'
    r'abstract|async|new|sealed|partial)\s+)+'
    r'(?:[\w<>\[\]?,\.]+\s+)*'
    r'(\w+)\s*(?:<[^>]*>)?\s*\('
)

_HUNK_HEADER_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)

_CLASS_DECL_RE = re.compile(
    r'^\s*(?:(?:public|protected|private|internal|static|abstract|sealed|'
    r'final|partial|new|data|open|inner|value|annotation|enum)\s+)*'
    r'(?:class|struct|record)\s+(\w+)'
)


class DotNetAdapter(LanguageAdapter):
    language = "dotnet"
    method_decl_re = _DOTNET_METHOD_RE
    marker_suffixes = (".csproj", ".sln")

    _INFRA_EXTS: Tuple[str, ...] = (".sln", ".csproj")
    _INFRA_NAMES: Tuple[str, ...] = (
        "global.json", "nuget.config",
        "directory.build.props", "directory.build.targets",
        "directory.packages.props", "directory.packages.lock.json",
        ".globalconfig",
    )
    _CONFIG_EXTS: Tuple[str, ...] = (
        ".json", ".xml", ".yaml", ".yml",
        ".config", ".resx", ".resw",
        ".razor", ".cshtml", ".aspx", ".ascx",
        ".proto", ".graphql",
    )

    def detect(self, root: Path) -> bool:
        return next(_iter_files(root, suffixes=(".csproj", ".sln")), None) is not None

    def has_build_file(self, directory: Path) -> bool:
        try:
            return any(
                f.suffix.lower() in (".csproj", ".sln")
                for f in directory.iterdir() if f.is_file()
            )
        except OSError:
            return False

    def classify(self, change: FileChange) -> ChangeCategory:
        p = change.path.lower()
        base = os.path.basename(p)
        ext = os.path.splitext(p)[1]
        if _in_hidden_dir(p):
            return ChangeCategory.IGNORED
        if ext in self._INFRA_EXTS or base in self._INFRA_NAMES:
            return ChangeCategory.INFRA
        if ext in IGNORED_EXTENSIONS or base in IGNORED_FILENAMES:
            return ChangeCategory.IGNORED
        if ext == ".cs":
            return ChangeCategory.SOURCE
        if ext in self._CONFIG_EXTS:
            return ChangeCategory.CONFIG
        return ChangeCategory.UNKNOWN

    def discover(self, root: Path) -> Tuple[List[Project], List[Path]]:
        path_to_name: Dict[Path, str] = {}
        slns: List[Path] = []

        for sln in sorted(_iter_files(root, suffixes=(".sln",))):
            slns.append(sln)
            try:
                content = sln.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            for m in _DOTNET_SLN_RE.finditer(content):
                name = m.group(1).strip()
                rel = m.group(2).strip().replace("\\", os.sep).replace("/", os.sep)
                abs_path = (sln.parent / rel).resolve()
                if abs_path.exists() and not _excluded(abs_path):
                    path_to_name.setdefault(abs_path, name)

        for csproj in sorted(_iter_files(root, suffixes=(".csproj",))):
            resolved = csproj.resolve()
            path_to_name.setdefault(resolved, resolved.stem)

        return [self._parse_csproj(name, path) for path, name in path_to_name.items()], slns

    def _parse_csproj(self, name: str, path: Path) -> Project:
        proj = Project(name=name, path=path)
        if name.lower().endswith(_DOTNET_TEST_SUFFIXES):
            proj.is_test_project = True
        try:
            xml_root = ET.parse(path).getroot()
            for elem in xml_root.iter("IsTestProject"):
                if (elem.text or "").strip().lower() == "true":
                    proj.is_test_project = True
            for ref in xml_root.iter("ProjectReference"):
                include = (ref.get("Include") or "").strip().replace("\\", "/")
                if not include:
                    continue
                try:
                    ref_path = (path.parent / include).resolve()
                except OSError:
                    ref_path = None
                if ref_path is not None and ref_path.exists():
                    if ref_path not in proj.reference_paths:
                        proj.reference_paths.append(ref_path)
                else:
                    # MSBuild variables etc. — fall back to stem matching
                    stem = Path(include).stem
                    if stem and stem not in proj.project_references:
                        proj.project_references.append(stem)
            for pkg in xml_root.iter("PackageReference"):
                if pkg.get("Include", "").lower().strip() in _DOTNET_TEST_PACKAGES:
                    proj.is_test_project = True
        except (ET.ParseError, OSError):
            pass
        return proj

    def build_test_file_cache(self, test_projects: List[Project]) -> Dict[Path, str]:
        cache: Dict[Path, str] = {}
        for proj in test_projects:
            for cs in _iter_files(proj.directory, suffixes=(".cs",)):
                if cs not in cache:
                    try:
                        cache[cs] = cs.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        pass
        return cache

    def is_test_file(self, path: str) -> bool:
        # .NET test projects contain only test code; any file in one IS a test
        return True

    def strategy_convention(
        self, change: FileChange, test_projects: List[Project],
    ) -> List[Tuple[Path, str]]:
        results: List[Tuple[Path, str]] = []
        seen: Set[Tuple[Path, str]] = set()
        for p in change.analysis_paths():
            if not p.lower().endswith(".cs"):
                continue
            stem = Path(p).stem
            candidates = [
                f"{stem}Tests", f"{stem}Test",
                f"{stem}Specs", f"{stem}Spec",
                f"Test{stem}", f"Tests{stem}",
            ]
            cand_by_fname = {f"{c}.cs".lower(): c for c in candidates}
            for proj in test_projects:
                for hit in _iter_files(proj.directory, filenames=frozenset(cand_by_fname)):
                    key = (proj.path, cand_by_fname[hit.name.lower()])
                    if key not in seen:
                        seen.add(key)
                        results.append(key)
        return results

    def strategy_symbol_search(
        self,
        change: FileChange,
        test_projects: List[Project],
        git_root: Path,
        cache: Dict[Path, str],
    ) -> List[Tuple[Path, str]]:
        if change.is_deleted:
            return []
        file_abs = (git_root / change.path).resolve()
        try:
            file_abs.relative_to(git_root)
        except ValueError:
            return []
        if not file_abs.exists() or file_abs.suffix.lower() != ".cs":
            return []
        try:
            source = file_abs.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        symbols = list(dict.fromkeys(_DOTNET_TYPE_DECL_RE.findall(source)))[:20]
        if not symbols:
            return []

        patterns = [re.compile(r'\b' + re.escape(s) + r'\b') for s in symbols]
        proj_files = {
            proj.path: [f for f in cache if _is_under(f, proj.directory)]
            for proj in test_projects
        }
        seen: Set[Tuple[Path, str]] = set()
        results: List[Tuple[Path, str]] = []
        for proj in test_projects:
            for cs_file in proj_files[proj.path]:
                content = cache[cs_file]
                for pat in patterns:
                    if pat.search(content):
                        m = _DOTNET_TEST_CLASS_RE.search(content)
                        cls = m.group(1) if m else cs_file.stem
                        key = (proj.path, cls)
                        if key not in seen:
                            seen.add(key)
                            results.append(key)
                        break
        return results

    def build_filter(self, test_ids: Set[str]) -> Tuple[str, bool]:
        if not test_ids:
            return "", False
        if len(test_ids) > FILTER_CLASS_LIMIT:
            return "", True
        return "|".join(f"FullyQualifiedName~{c}" for c in sorted(test_ids)), False

    def _project_classes(self, proj_path: str, classes: Set[str]) -> Set[str]:
        """Scope class filters to this project — the global filter set spans
        every affected project, and a --filter matching nothing skips the
        project's tests. Empty result → callers run the project unfiltered."""
        stems = {
            f.stem for f in _iter_files(Path(proj_path).parent, suffixes=(".cs",))
        }
        return {c for c in classes if c.split(".")[0] in stems}

    def _project_filter(self, proj_path: str, result: ImpactResult) -> str:
        if not result.test_filter:
            return ""
        scoped = self._project_classes(proj_path, result.affected_test_classes)
        if not scoped:
            return ""
        return "|".join(f"FullyQualifiedName~{c}" for c in sorted(scoped))

    def extract_test_identifiers(self, file_path: Path, content: str) -> List[str]:
        return _DOTNET_TEST_CLASS_RE.findall(content)

    def run_tests(
        self, result: ImpactResult, extra_args: List[str], cwd: Optional[Path],
    ) -> int:
        if result.run_all and not result.test_filter:
            if result.workspace_files:
                code = 0
                for sln in result.workspace_files:
                    cmd = ["dotnet", "test", sln, *extra_args]
                    print(f"\n[RUN] {' '.join(cmd)}\n")
                    rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
                    if rc != 0:
                        code = rc
                return code
            cmd = ["dotnet", "test", *extra_args]
            print(f"\n[RUN] {' '.join(cmd)}\n")
            return subprocess.call(cmd, cwd=str(cwd) if cwd else None)

        if not result.test_project_paths:
            print("[INFO] No tests to run.", file=sys.stderr)
            return 0

        code = 0
        for proj in result.test_project_paths:
            proj_filter = self._project_filter(proj, result)
            filter_args = ["--filter", proj_filter] if proj_filter else []
            cmd = ["dotnet", "test", proj, *extra_args, *filter_args]
            print(f"\n[RUN] {' '.join(cmd)}\n")
            rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
            if rc != 0:
                code = rc
        return code

    def fmt_command(self, result: ImpactResult) -> str:
        if result.run_all and not result.test_filter:
            if result.workspace_files:
                return " && ".join(f'dotnet test "{s}"' for s in result.workspace_files)
            return "dotnet test"
        if not result.test_project_paths:
            return "(no tests to run)"
        parts = []
        for p in result.test_project_paths:
            proj_filter = self._project_filter(p, result)
            filter_part = f' --filter "{proj_filter}"' if proj_filter else ""
            parts.append(f'dotnet test "{p}"{filter_part}')
        return " && ".join(parts)


# ---------------------------------------------------------------------------
# Java adapter  (Maven + Gradle)
# ---------------------------------------------------------------------------

_JAVA_TEST_PACKAGES: Set[str] = {
    "junit", "junit-jupiter", "junit-jupiter-api", "junit-jupiter-engine",
    "junit-vintage-engine", "junit-platform-launcher",
    "testng",
    "mockito-core", "mockito-junit-jupiter", "mockito-inline",
    "assertj-core", "hamcrest", "hamcrest-core", "hamcrest-library",
    "truth", "rest-assured",
    # Android / Kotlin
    "robolectric", "mockk", "espresso-core", "androidx.test",
    "turbine", "kotlin-test", "kotest",
}

_JAVA_TYPE_DECL_RE = re.compile(
    r'\b(?:public|protected)\s+'
    r'(?:(?:abstract|static|final|sealed|non-sealed)\s+)*'
    r'(?:class|interface|enum|record|@interface)\s+(\w+)'
)

# Kotlin types are public by default — no modifier required.
_KOTLIN_TYPE_DECL_RE = re.compile(
    r'(?:^|\n)[ \t]*(?:@\w+(?:\([^)]*\))?[ \t]+)*'
    r'(?:(?:public|internal|private|protected|abstract|final|open|sealed|'
    r'data|inner|value|annotation|enum|expect|actual)\s+)*'
    r'(?:class|interface|object)\s+(\w+)'
)

_JAVA_TEST_CLASS_RE = re.compile(r'\bclass\s+(\w+)')

# Matches Java method declarations (requires at least one modifier — bare
# `Type name(` would also match call sites) and Kotlin fun declarations
# (anchored by the `fun` keyword; modifiers optional, public by default).
_JAVA_METHOD_RE = re.compile(
    r'^\s*'
    r'(?:@\w+(?:\([^)]*\))?\s+)*'
    r'(?:'
    r'(?:(?:public|internal|private|protected|open|override|suspend|inline|'
    r'operator|infix|tailrec|actual|expect)\s+)*'
    # optional generics, then optional extension receiver(s): fun String.toSlug(
    r'fun\s+(?:<[^>]*>\s+)?(?:\w+(?:<[^>]*>)?\??\.)*(?P<kt>\w+)\s*\('
    r'|'
    r'(?:(?:public|protected|private|static|final|abstract|synchronized|'
    r'native|default|strictfp)\s+)+'
    r'(?:<[^>]*>\s+)?'
    r'(?:[\w<>\[\]?,\.]+\s+)*'
    r'(?P<jv>\w+)\s*\('
    r')'
)


def _method_name(m: "re.Match") -> str:
    """Method name from a method_decl_re match — handles both the named
    kt/jv alternation groups and plain single-group regexes (.NET)."""
    gd = m.groupdict()
    if gd:
        return gd.get("kt") or gd.get("jv") or m.group(1)
    return m.group(1)


class JavaAdapter(LanguageAdapter):
    language = "java"
    method_decl_re = _JAVA_METHOD_RE

    _SOURCE_EXTS: Tuple[str, ...] = (".java", ".kt", ".groovy", ".scala")
    _INFRA_NAMES: Tuple[str, ...] = (
        "pom.xml", "build.gradle", "build.gradle.kts",
        "settings.gradle", "settings.gradle.kts",
        "gradle.properties", "gradle-wrapper.properties",
        "gradlew", "gradlew.bat",
        "libs.versions.toml",       # Gradle version catalog
    )
    _CONFIG_EXTS: Tuple[str, ...] = (
        ".xml", ".yaml", ".yml", ".json",
        ".properties", ".toml", ".ini",
        ".pro",                     # proguard / R8 rules
    )
    # src/androidTest holds device-run (instrumented) tests; src/test runs on the JVM
    _TEST_DIR_RELS: Tuple[str, ...] = (
        "src/test/java", "src/test/kotlin", "src/test/groovy",
        "src/androidTest/java", "src/androidTest/kotlin",
    )

    _BUILD_FILES: FrozenSet[str] = frozenset(
        {"pom.xml", "build.gradle", "build.gradle.kts"}
    )
    marker_filenames = _BUILD_FILES

    def detect(self, root: Path) -> bool:
        return next(_iter_files(root, filenames=self._BUILD_FILES), None) is not None

    def has_build_file(self, directory: Path) -> bool:
        return any(
            (directory / name).is_file()
            for name in ("pom.xml", "build.gradle", "build.gradle.kts",
                         "settings.gradle", "settings.gradle.kts")
        )

    def classify(self, change: FileChange) -> ChangeCategory:
        p = change.path.lower()
        base = os.path.basename(p)
        ext = os.path.splitext(p)[1]
        if _in_hidden_dir(p):
            return ChangeCategory.IGNORED
        if base in self._INFRA_NAMES:
            return ChangeCategory.INFRA
        if ext in IGNORED_EXTENSIONS or base in IGNORED_FILENAMES:
            return ChangeCategory.IGNORED
        if ext in self._SOURCE_EXTS:
            return ChangeCategory.SOURCE
        if ext in self._CONFIG_EXTS:
            return ChangeCategory.CONFIG
        return ChangeCategory.UNKNOWN

    def _parse_pom(self, pom_path: Path) -> Project:
        name = pom_path.parent.name
        is_test = False
        refs: List[str] = []
        group = ""

        if (pom_path.parent / "src" / "test" / "java").exists():
            is_test = True
        if (pom_path.parent / "src" / "test" / "kotlin").exists():
            is_test = True

        try:
            root_el = ET.parse(pom_path).getroot()
            ns = root_el.tag.split("}")[0].lstrip("{") if "}" in root_el.tag else ""
            pfx = f"{{{ns}}}" if ns else ""

            def _find_text(tag: str) -> Optional[str]:
                el = root_el.find(f"{pfx}{tag}")
                if el is None:
                    el = root_el.find(tag)
                return (el.text or "").strip() if el is not None else None

            artifact = _find_text("artifactId")
            if artifact:
                name = artifact

            group = _find_text("groupId") or ""
            if not group:
                # groupId is commonly inherited from <parent>
                parent_el = root_el.find(f"{pfx}parent")
                if parent_el is None:
                    parent_el = root_el.find("parent")
                if parent_el is not None:
                    g_el = parent_el.find(f"{pfx}groupId")
                    if g_el is None:
                        g_el = parent_el.find("groupId")
                    if g_el is not None:
                        group = (g_el.text or "").strip()

            deps_el = root_el.find(f"{pfx}dependencies")
            if deps_el is None:
                deps_el = root_el.find("dependencies")
            for dep in (list(deps_el) if deps_el is not None else []):
                art_el = dep.find(f"{pfx}artifactId")
                if art_el is None:
                    art_el = dep.find("artifactId")
                scope_el = dep.find(f"{pfx}scope")
                if scope_el is None:
                    scope_el = dep.find("scope")
                g_el = dep.find(f"{pfx}groupId")
                if g_el is None:
                    g_el = dep.find("groupId")
                art = (art_el.text or "").lower().strip() if art_el is not None else ""
                scope = (scope_el.text or "").lower().strip() if scope_el is not None else ""
                dep_group = (g_el.text or "").lower().strip() if g_el is not None else ""
                if dep_group in ("${project.groupid}", "${pom.groupid}"):
                    dep_group = group.lower()
                if art in _JAVA_TEST_PACKAGES or scope == "test":
                    is_test = True
                ref = f"{dep_group}:{art}" if dep_group else art
                if art and ref not in refs:
                    refs.append(ref)
        except (ET.ParseError, OSError):
            pass

        return Project(
            name=name, path=pom_path, is_test_project=is_test,
            project_references=refs, group_id=group,
        )

    def _parse_gradle(self, gradle_path: Path) -> Project:
        name = gradle_path.parent.name
        is_test = False
        refs: List[str] = []

        for td_rel in self._TEST_DIR_RELS:
            if (gradle_path.parent / td_rel.replace("/", os.sep)).exists():
                is_test = True
                break

        try:
            content = gradle_path.read_text(encoding="utf-8", errors="replace")
            # Match individual dependency lines: testImplementation 'junit:junit:4.13'
            _dep_re = re.compile(
                r'\b(testImplementation|testCompileOnly|testRuntimeOnly|testApi)\b'
                r'[^\n]*?(["\'])([^"\']+)\2'
            )
            for dep_m in _dep_re.finditer(content):
                coord = dep_m.group(3).lower()
                if any(pkg in coord for pkg in _JAVA_TEST_PACKAGES):
                    is_test = True
                    break
            # Module paths may be nested (":core:model") — ':' must be part
            # of the captured path.
            for m in re.finditer(r"project\s*\(\s*['\"]:?([\w\-/.:]+)['\"]\s*\)", content):
                dep = m.group(1).lstrip(":").replace(":", "/")
                if dep not in refs:
                    refs.append(dep)
        except OSError:
            pass

        return Project(name=name, path=gradle_path, is_test_project=is_test, project_references=refs)

    def discover(self, root: Path) -> Tuple[List[Project], List[Path]]:
        seen: Set[Path] = set()
        projects: List[Project] = []
        workspace_files: List[Path] = []

        poms: List[Path] = []
        gradles: List[Path] = []
        for bf in sorted(_iter_files(root, filenames=self._BUILD_FILES)):
            (poms if bf.name.lower() == "pom.xml" else gradles).append(bf)

        for pom in poms:
            resolved = pom.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            projects.append(self._parse_pom(resolved))

        root_pom = (root / "pom.xml").resolve()
        if root_pom.exists():
            workspace_files.append(root_pom)

        gradle_projects: List[Project] = []
        for gradle in gradles:
            resolved = gradle.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            proj = self._parse_gradle(resolved)
            projects.append(proj)
            gradle_projects.append(proj)

        # Resolve project(":a:b") refs to build-file paths relative to the
        # gradle root — the settings.gradle location nearest the referring
        # module, which is not necessarily --root. Name matching can't see
        # nested module paths (the project name is just the directory name);
        # unresolved refs keep their name for fallback matching.
        for proj in gradle_projects:
            base = self._gradle_root(proj.directory) or root
            remaining: List[str] = []
            for ref in proj.project_references:
                cand_dir = base.joinpath(*ref.split("/"))
                for bf_name in ("build.gradle", "build.gradle.kts"):
                    cand = cand_dir / bf_name
                    if cand.exists():
                        rp = cand.resolve()
                        if rp not in proj.reference_paths:
                            proj.reference_paths.append(rp)
                        break
                else:
                    remaining.append(ref)
            proj.project_references = remaining

        for sf in ("settings.gradle", "settings.gradle.kts"):
            sf_path = root / sf
            if sf_path.exists():
                workspace_files.append(sf_path)

        return projects, workspace_files

    def build_test_file_cache(self, test_projects: List[Project]) -> Dict[Path, str]:
        cache: Dict[Path, str] = {}
        for proj in test_projects:
            for test_dir_rel in self._TEST_DIR_RELS:
                test_dir = proj.directory / test_dir_rel.replace("/", os.sep)
                if test_dir.exists():
                    for f in _iter_files(test_dir, suffixes=self._SOURCE_EXTS):
                        if f not in cache:
                            try:
                                cache[f] = f.read_text(encoding="utf-8", errors="replace")
                            except OSError:
                                pass
        return cache

    def is_test_file(self, path: str) -> bool:
        norm = path.replace("\\", "/")
        return "src/test/" in norm or "src/androidTest/" in norm

    def strategy_convention(
        self, change: FileChange, test_projects: List[Project],
    ) -> List[Tuple[Path, str]]:
        results: List[Tuple[Path, str]] = []
        seen: Set[Tuple[Path, str]] = set()
        for p in change.analysis_paths():
            if not any(p.lower().endswith(ext) for ext in self._SOURCE_EXTS):
                continue
            if self.is_test_file(p):
                continue
            stem = Path(p).stem
            candidates = [f"{stem}Test", f"{stem}Tests", f"{stem}IT", f"{stem}Spec"]
            cand_by_stem = {c.lower(): c for c in candidates}
            for proj in test_projects:
                for td_rel in self._TEST_DIR_RELS:
                    td = proj.directory / td_rel.replace("/", os.sep)
                    if not td.exists():
                        continue
                    for hit in _iter_files(td, suffixes=self._SOURCE_EXTS):
                        cand = cand_by_stem.get(hit.stem.lower())
                        if cand:
                            key = (proj.path, cand)
                            if key not in seen:
                                seen.add(key)
                                results.append(key)
        return results

    def strategy_symbol_search(
        self,
        change: FileChange,
        test_projects: List[Project],
        git_root: Path,
        cache: Dict[Path, str],
    ) -> List[Tuple[Path, str]]:
        if change.is_deleted:
            return []
        file_abs = (git_root / change.path).resolve()
        try:
            file_abs.relative_to(git_root)
        except ValueError:
            return []
        if not file_abs.exists() or file_abs.suffix.lower() not in self._SOURCE_EXTS:
            return []
        try:
            source = file_abs.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        type_re = (
            _KOTLIN_TYPE_DECL_RE
            if file_abs.suffix.lower() in (".kt", ".kts")
            else _JAVA_TYPE_DECL_RE
        )
        symbols = list(dict.fromkeys(type_re.findall(source)))[:20]
        if not symbols:
            return []

        patterns = [re.compile(r'\b' + re.escape(s) + r'\b') for s in symbols]
        proj_files = {
            proj.path: [f for f in cache if _is_under(f, proj.directory)]
            for proj in test_projects
        }
        seen: Set[Tuple[Path, str]] = set()
        results: List[Tuple[Path, str]] = []
        for proj in test_projects:
            for java_file in proj_files[proj.path]:
                content = cache[java_file]
                for pat in patterns:
                    if pat.search(content):
                        m = _JAVA_TEST_CLASS_RE.search(content)
                        cls = m.group(1) if m else java_file.stem
                        key = (proj.path, cls)
                        if key not in seen:
                            seen.add(key)
                            results.append(key)
                        break
        return results

    def build_filter(self, test_ids: Set[str]) -> Tuple[str, bool]:
        if not test_ids:
            return "", False
        if len(test_ids) > FILTER_CLASS_LIMIT:
            return "", True
        # Maven Surefire uses # for method separator (Class#method), while the
        # internal representation uses dot (Class.method) for Gradle compatibility.
        surefire = [
            tid.replace(".", "#", 1) if "." in tid else tid
            for tid in sorted(test_ids)
        ]
        return ",".join(surefire), False

    def extract_test_identifiers(self, file_path: Path, content: str) -> List[str]:
        return _JAVA_TEST_CLASS_RE.findall(content)

    def _is_gradle_project(self, proj_path: str) -> bool:
        d = Path(proj_path).parent
        return (d / "build.gradle").exists() or (d / "build.gradle.kts").exists()

    @staticmethod
    def _gradle_root(start: Path) -> Optional[Path]:
        """Nearest ancestor of start (inclusive) containing settings.gradle.
        Bounded by the repository: never walks above a directory containing
        .git — a stray settings file outside the repo must not win."""
        cur = start
        while True:
            if (cur / "settings.gradle").exists() or (cur / "settings.gradle.kts").exists():
                return cur
            if (cur / ".git").exists() or cur.parent == cur:
                return None
            cur = cur.parent

    def _gradle_module_path(self, proj_path: str) -> str:
        """Gradle path of the module (e.g. 'core:model') — the directory path
        relative to the settings.gradle root, colon-joined. Empty string for
        the root module; module dir name when no settings file is found."""
        d = Path(proj_path).parent
        groot = self._gradle_root(d)
        if groot is None:
            return d.name
        return ":".join(d.relative_to(groot).parts)

    def _module_classes(
        self, proj_path: str, classes: Set[str],
    ) -> Tuple[Set[str], Set[str]]:
        """Scope class filters to this module and split into (unit,
        instrumented). The global filter set spans every affected module; a
        filter naming a class from another module would fail the task. A
        class is assigned by which of the module's test dirs holds its file;
        instrumented classes (src/androidTest) need the connectedAndroidTest
        task. Classes matching neither dir are dropped for this module —
        callers fall back to the module's full suite when nothing remains."""
        proj_dir = Path(proj_path).parent
        unit_names: Set[str] = set()
        instr_names: Set[str] = set()
        for td_rel in self._TEST_DIR_RELS:
            d = proj_dir / td_rel.replace("/", os.sep)
            if not d.exists():
                continue
            names = {f.stem for f in _iter_files(d, suffixes=self._SOURCE_EXTS)}
            if "androidTest" in td_rel:
                instr_names |= names
            else:
                unit_names |= names
        unit = {c for c in classes if c.split(".")[0] in unit_names}
        instr = {c for c in classes if c.split(".")[0] in instr_names}
        return unit, instr

    def _has_gradlew(self, cwd: Optional[Path]) -> bool:
        base = cwd or Path(".")
        return (base / "gradlew").exists() or (base / "gradlew.bat").exists()

    def run_tests(
        self, result: ImpactResult, extra_args: List[str], cwd: Optional[Path],
    ) -> int:
        if result.run_all and not result.test_filter:
            is_gradle = any("gradle" in Path(f).name.lower() for f in result.workspace_files)
            if is_gradle:
                gradle = "./gradlew" if self._has_gradlew(cwd) else "gradle"
                cmd = [gradle, "test", *extra_args]
            else:
                cmd = ["mvn", "test", *extra_args]
            print(f"\n[RUN] {' '.join(cmd)}\n")
            return subprocess.call(cmd, cwd=str(cwd) if cwd else None)

        if not result.test_project_paths:
            print("[INFO] No tests to run.", file=sys.stderr)
            return 0

        # Project names run parallel to paths in ImpactResult; Maven's -pl
        # selector needs the artifactId (the name), not the directory name.
        name_by_path = dict(zip(result.test_project_paths, result.affected_test_projects))
        code = 0
        for proj_path in result.test_project_paths:
            module_name = name_by_path.get(proj_path, Path(proj_path).parent.name)
            is_gradle = self._is_gradle_project(proj_path)
            cmds: List[List[str]] = []
            if is_gradle:
                gradle = "./gradlew" if self._has_gradlew(cwd) else "gradle"
                mp = self._gradle_module_path(proj_path)
                test_task = f":{mp}:test" if mp else "test"
                connected_task = f":{mp}:connectedAndroidTest" if mp else "connectedAndroidTest"
                if result.test_filter:
                    unit, instr = self._module_classes(
                        proj_path, result.affected_test_classes
                    )
                    if unit:
                        cmds.append([
                            gradle, test_task,
                            *(f"--tests={c}" for c in sorted(unit)), *extra_args,
                        ])
                    if instr:
                        cmds.append([
                            gradle, connected_task,
                            *(f"--tests={c}" for c in sorted(instr)), *extra_args,
                        ])
                if not cmds:
                    cmds.append([gradle, test_task, *extra_args])
            else:
                filter_args: List[str] = []
                if result.test_filter:
                    unit, _ = self._module_classes(
                        proj_path, result.affected_test_classes
                    )
                    if unit:
                        surefire = ",".join(
                            c.replace(".", "#", 1) if "." in c else c
                            for c in sorted(unit)
                        )
                        filter_args = [f"-Dtest={surefire}"]
                cmds.append(["mvn", "test", "-pl", f":{module_name}", *filter_args, *extra_args])
            for cmd in cmds:
                print(f"\n[RUN] {' '.join(cmd)}\n")
                rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
                if rc != 0:
                    code = rc
        return code

    def fmt_command(self, result: ImpactResult) -> str:
        is_gradle = any("gradle" in Path(f).name.lower() for f in result.workspace_files)
        if result.run_all and not result.test_filter:
            return "./gradlew test" if is_gradle else "mvn test"
        if not result.test_project_paths:
            return "(no tests to run)"
        parts = []
        name_by_path = dict(zip(result.test_project_paths, result.affected_test_projects))
        for proj_path in result.test_project_paths:
            module_name = name_by_path.get(proj_path, Path(proj_path).parent.name)
            gradle = self._is_gradle_project(proj_path)
            if gradle:
                mp = self._gradle_module_path(proj_path)
                test_task = f":{mp}:test" if mp else "test"
                connected_task = f":{mp}:connectedAndroidTest" if mp else "connectedAndroidTest"
                if result.test_filter:
                    unit, instr = self._module_classes(
                        proj_path, result.affected_test_classes
                    )
                    if unit:
                        filters = " ".join(f'--tests="{c}"' for c in sorted(unit))
                        parts.append(f'./gradlew {test_task} {filters}')
                    if instr:
                        filters = " ".join(f'--tests="{c}"' for c in sorted(instr))
                        parts.append(f'./gradlew {connected_task} {filters}')
                    if not unit and not instr:
                        parts.append(f'./gradlew {test_task}')
                else:
                    parts.append(f'./gradlew {test_task}')
            else:
                filter_str = ""
                if result.test_filter:
                    unit, _ = self._module_classes(
                        proj_path, result.affected_test_classes
                    )
                    if unit:
                        surefire = ",".join(
                            c.replace(".", "#", 1) if "." in c else c
                            for c in sorted(unit)
                        )
                        filter_str = f' -Dtest="{surefire}"'
                parts.append(f'mvn test -pl ":{module_name}"{filter_str}')
        return " && ".join(parts)


# ---------------------------------------------------------------------------
# Node.js adapter  (Jest / Vitest / Mocha)
# ---------------------------------------------------------------------------

_NODE_TEST_RUNNERS: Set[str] = {
    "jest", "@jest/core", "jest-circus",
    "vitest",
    "mocha",
    "jasmine", "jasmine-core",
    "ava",
}

_NODE_SYMBOL_RE = re.compile(
    r'\bexport\s+(?:default\s+)?'
    r'(?:(?:abstract|async|declare)\s+)*'
    r'(?:class|function\*?|const|let|var|interface|type|enum)\s+(\w+)'
)


class NodeAdapter(LanguageAdapter):
    language = "node"
    marker_filenames = frozenset({"package.json"})

    _SOURCE_EXTS: Tuple[str, ...] = (
        ".js", ".ts", ".jsx", ".tsx",
        ".mjs", ".cjs", ".mts", ".cts",
    )
    _INFRA_NAMES: Tuple[str, ...] = (
        "package.json",
        "tsconfig.json", "tsconfig.base.json",
        "jest.config.js", "jest.config.ts", "jest.config.mjs", "jest.config.cjs",
        "vitest.config.js", "vitest.config.ts", "vitest.config.mts",
        "webpack.config.js", "webpack.config.ts",
        "vite.config.js", "vite.config.ts",
        "rollup.config.js", "rollup.config.ts",
        "babel.config.js", "babel.config.json",
        ".babelrc", ".babelrc.js",
        "eslint.config.js", ".eslintrc", ".eslintrc.js", ".eslintrc.json",
        ".prettierrc", ".prettierrc.js", ".prettierrc.json",
        "nx.json", "turbo.json", "lerna.json", "pnpm-workspace.yaml",
    )
    _CONFIG_EXTS: Tuple[str, ...] = (".json", ".yaml", ".yml", ".env", ".toml")

    def detect(self, root: Path) -> bool:
        # Nested search: in polyglot repos the package.json may live in a
        # sub-app (e.g. a frontend/ folder next to a Maven backend).
        return next(_iter_files(
            root, filenames=frozenset({"package.json"}), excluded=_NODE_EXCLUDED_DIRS,
        ), None) is not None

    def has_build_file(self, directory: Path) -> bool:
        return (directory / "package.json").is_file()

    def classify(self, change: FileChange) -> ChangeCategory:
        p = change.path.lower()
        base = os.path.basename(p)
        ext = os.path.splitext(p)[1]
        if _in_hidden_dir(p):
            return ChangeCategory.IGNORED
        if base in self._INFRA_NAMES:
            return ChangeCategory.INFRA
        if ext in IGNORED_EXTENSIONS or base in IGNORED_FILENAMES:
            return ChangeCategory.IGNORED
        if ext in self._SOURCE_EXTS:
            return ChangeCategory.SOURCE
        if ext in self._CONFIG_EXTS:
            return ChangeCategory.CONFIG
        return ChangeCategory.UNKNOWN

    def _parse_package_json(self, pkg_path: Path) -> Tuple[Project, Set[str]]:
        """Returns (project, all_dependency_names). Dependency names are used
        by discover() to wire plain-version internal deps to sibling packages."""
        name = pkg_path.parent.name
        is_test = False
        refs: List[str] = []
        dep_names: Set[str] = set()
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
            name = data.get("name", name) or name
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            dep_names = set(all_deps)
            if any(r in {k.lower() for k in all_deps} for r in _NODE_TEST_RUNNERS):
                is_test = True
            if "test" in (data.get("scripts") or {}):
                is_test = True
            for dep, ver in all_deps.items():
                if str(ver).startswith(("workspace:", "file:")):
                    refs.append(dep)
        except (json.JSONDecodeError, OSError):
            pass
        proj = Project(name=name, path=pkg_path, is_test_project=is_test, project_references=refs)
        return proj, dep_names

    def discover(self, root: Path) -> Tuple[List[Project], List[Path]]:
        seen: Set[Path] = set()
        projects: List[Project] = []
        workspace_files: List[Path] = []

        root_pkg = root / "package.json"
        is_workspace_root = False
        if root_pkg.exists():
            workspace_files.append(root_pkg.resolve())
            try:
                data = json.loads(root_pkg.read_text(encoding="utf-8", errors="replace"))
                is_workspace_root = bool(data.get("workspaces"))
            except (json.JSONDecodeError, OSError):
                pass
        # pnpm and lerna define the workspace outside package.json
        if (root / "pnpm-workspace.yaml").exists() or (root / "lerna.json").exists():
            is_workspace_root = True

        parsed: List[Tuple[Project, Set[str]]] = []
        for pkg in sorted(_iter_files(
            root, filenames=frozenset({"package.json"}), excluded=_NODE_EXCLUDED_DIRS,
        )):
            resolved = pkg.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            parsed.append(self._parse_package_json(resolved))
        projects = [proj for proj, _ in parsed]

        # Internal deps declared with plain version ranges (lerna / classic
        # yarn): wire an edge when the dep name matches a sibling package.
        package_names = {p.name for p in projects}
        for proj, dep_names in parsed:
            for dep in dep_names:
                if (
                    dep in package_names
                    and dep != proj.name
                    and dep not in proj.project_references
                ):
                    proj.project_references.append(dep)

        if is_workspace_root:
            root_resolved = root_pkg.resolve()
            for proj in projects:
                if proj.path == root_resolved:
                    # workspace root is the runner, not a test project itself
                    proj.is_test_project = False
                elif not proj.is_test_project:
                    # mark sub-package as test project if it owns test files
                    has_tests = any(
                        self.is_test_file(str(f))
                        for f in _iter_files(
                            proj.directory,
                            suffixes=self._SOURCE_EXTS,
                            excluded=_NODE_EXCLUDED_DIRS,
                        )
                    )
                    if has_tests:
                        proj.is_test_project = True

        # Single-package repo: mark the only project as test-capable
        if projects and not any(p.is_test_project for p in projects):
            for p in projects:
                p.is_test_project = True

        return projects, workspace_files

    def build_test_file_cache(self, test_projects: List[Project]) -> Dict[Path, str]:
        cache: Dict[Path, str] = {}
        for proj in test_projects:
            for f in _iter_files(
                proj.directory, suffixes=self._SOURCE_EXTS, excluded=_NODE_EXCLUDED_DIRS,
            ):
                if self.is_test_file(str(f)) and f not in cache:
                    try:
                        cache[f] = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        pass
        return cache

    def is_test_file(self, path: str) -> bool:
        norm = path.replace("\\", "/").lower()
        return ".test." in norm or ".spec." in norm or "/__tests__/" in norm

    def strategy_convention(
        self, change: FileChange, test_projects: List[Project],
    ) -> List[Tuple[Path, str]]:
        results: List[Tuple[Path, str]] = []
        seen: Set[Tuple[Path, str]] = set()
        for p in change.analysis_paths():
            if not any(p.lower().endswith(ext) for ext in self._SOURCE_EXTS):
                continue
            if self.is_test_file(p):
                continue
            src = Path(p)
            stem = src.stem
            ext = src.suffix
            direct_names = frozenset({
                f"{stem}.test{ext}".lower(), f"{stem}.spec{ext}".lower(),
                f"{stem}.test.ts", f"{stem}.spec.ts",
                f"{stem}.test.js", f"{stem}.spec.js",
            })
            tests_dir_names = frozenset(f"{stem}{t}".lower() for t in self._SOURCE_EXTS)
            for proj in test_projects:
                direct_hit: Optional[Path] = None
                tests_hit: Optional[Path] = None
                for f in _iter_files(
                    proj.directory, suffixes=self._SOURCE_EXTS, excluded=_NODE_EXCLUDED_DIRS,
                ):
                    name = f.name.lower()
                    if direct_hit is None and name in direct_names:
                        direct_hit = f
                    if tests_hit is None and f.parent.name == "__tests__" and name in tests_dir_names:
                        tests_hit = f
                    if direct_hit and tests_hit:
                        break
                for hit in (direct_hit, tests_hit):
                    if hit:
                        key = (proj.path, hit.stem)
                        if key not in seen:
                            seen.add(key)
                            results.append(key)
        return results

    def strategy_symbol_search(
        self,
        change: FileChange,
        test_projects: List[Project],
        git_root: Path,
        cache: Dict[Path, str],
    ) -> List[Tuple[Path, str]]:
        if change.is_deleted:
            return []
        file_abs = (git_root / change.path).resolve()
        try:
            file_abs.relative_to(git_root)
        except ValueError:
            return []
        if not file_abs.exists() or file_abs.suffix.lower() not in self._SOURCE_EXTS:
            return []
        try:
            source = file_abs.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        symbols = list(dict.fromkeys(_NODE_SYMBOL_RE.findall(source)))
        # Add the module name itself — tests often import from './moduleName'
        if file_abs.stem not in symbols:
            symbols.insert(0, file_abs.stem)
        symbols = symbols[:20]

        patterns = [re.compile(r'\b' + re.escape(s) + r'\b') for s in symbols]
        proj_files = {
            proj.path: [f for f in cache if _is_under(f, proj.directory)]
            for proj in test_projects
        }
        seen: Set[Tuple[Path, str]] = set()
        results: List[Tuple[Path, str]] = []
        for proj in test_projects:
            for test_file in proj_files[proj.path]:
                content = cache[test_file]
                for pat in patterns:
                    if pat.search(content):
                        test_id = test_file.stem
                        key = (proj.path, test_id)
                        if key not in seen:
                            seen.add(key)
                            results.append(key)
                        break
        return results

    def build_filter(self, test_ids: Set[str]) -> Tuple[str, bool]:
        if not test_ids:
            return "", False
        if len(test_ids) > FILTER_CLASS_LIMIT:
            return "", True
        return "|".join(re.escape(t) for t in sorted(test_ids)), False

    def extract_test_identifiers(self, file_path: Path, content: str) -> List[str]:
        return [file_path.stem]

    def prefer_run_all_when_all_affected(self) -> bool:
        return False  # always use --testPathPattern; npx jest alone runs everything

    def fill_missing_test_classes(
        self,
        affected_test_paths: Set[Path],
        affected_classes: Set[str],
        projects: List[Project],
    ) -> Set[str]:
        """For workspace packages transitively affected but with no specific class entry,
        inject all test IDs from those packages so the filter covers them."""
        path_to_proj = {p.path: p for p in projects}
        result = set(affected_classes)
        for test_path in affected_test_paths:
            proj = path_to_proj.get(test_path)
            if proj is None:
                continue
            proj_test_ids: Set[str] = set()
            for f in _iter_files(
                proj.directory, suffixes=self._SOURCE_EXTS, excluded=_NODE_EXCLUDED_DIRS,
            ):
                if self.is_test_file(str(f)):
                    proj_test_ids.add(f.stem)
            if proj_test_ids and not proj_test_ids.intersection(result):
                result.update(proj_test_ids)
        return result

    def _detect_runner(self, result: ImpactResult) -> str:
        has_test_script = False
        for pkg_path in result.test_project_paths + result.workspace_files:
            try:
                data = json.loads(Path(pkg_path).read_text(encoding="utf-8", errors="replace"))
                all_keys = {
                    k.lower() for k in
                    {**data.get("dependencies", {}), **data.get("devDependencies", {})}.keys()
                }
                if "vitest" in all_keys:
                    return "vitest"
                if "jest" in all_keys or "@jest/core" in all_keys:
                    return "jest"
                if "test" in (data.get("scripts") or {}):
                    has_test_script = True
            except (json.JSONDecodeError, OSError):
                pass
        # No known runner but a test script exists (karma, mocha via script,
        # ng test, ...) — defer to the package's own script. Path filtering
        # is not possible, so affected packages run their full suites.
        return "npm" if has_test_script else "jest"

    def run_tests(
        self, result: ImpactResult, extra_args: List[str], cwd: Optional[Path],
    ) -> int:
        runner = self._detect_runner(result)
        # Always run from workspace root when available; fall back to first test project dir
        run_dir = (
            Path(result.workspace_files[0]).parent if result.workspace_files
            else Path(result.test_project_paths[0]).parent if result.test_project_paths
            else cwd
        )
        if runner == "npm":
            if not result.test_project_paths:
                cmd = ["npm", "test", *extra_args]
                print(f"\n[RUN] {' '.join(cmd)}\n")
                return subprocess.call(cmd, cwd=str(run_dir) if run_dir else None)
            code = 0
            for pkg in result.test_project_paths:
                pkg_dir = Path(pkg).parent
                cmd = ["npm", "test", *extra_args]
                print(f"\n[RUN] {' '.join(cmd)}  (in {pkg_dir})\n")
                rc = subprocess.call(cmd, cwd=str(pkg_dir))
                if rc != 0:
                    code = rc
            return code
        if result.run_all:
            cmd = (
                ["npx", "vitest", "run", *extra_args]
                if runner == "vitest"
                else ["npx", "jest", *extra_args]
            )
            print(f"\n[RUN] {' '.join(cmd)}\n")
            return subprocess.call(cmd, cwd=str(run_dir) if run_dir else None)

        if not result.test_project_paths:
            print("[INFO] No tests to run.", file=sys.stderr)
            return 0

        if runner == "vitest":
            cmd = (
                ["npx", "vitest", "run", result.test_filter, *extra_args]
                if result.test_filter
                else ["npx", "vitest", "run", *extra_args]
            )
        else:
            # Positional pattern works on every jest major; --testPathPattern
            # was renamed in Jest 30.
            cmd = (
                ["npx", "jest", result.test_filter, *extra_args]
                if result.test_filter
                else ["npx", "jest", *extra_args]
            )
        print(f"\n[RUN] {' '.join(cmd)}\n")
        return subprocess.call(cmd, cwd=str(run_dir) if run_dir else None)

    def fmt_command(self, result: ImpactResult) -> str:
        runner = self._detect_runner(result)
        if runner == "npm":
            if not result.test_project_paths:
                return "npm test"
            return " && ".join(
                f'npm test --prefix "{Path(p).parent}"'
                for p in result.test_project_paths
            )
        base = f"npx {runner}" + (" run" if runner == "vitest" else "")
        if result.run_all:
            return base
        if not result.test_project_paths:
            return "(no tests to run)"
        return f'{base} "{result.test_filter}"' if result.test_filter else base


# ---------------------------------------------------------------------------
# Adapter detection
# ---------------------------------------------------------------------------

_ADAPTERS: List[LanguageAdapter] = [DotNetAdapter(), JavaAdapter(), NodeAdapter()]


def detect_adapters(root: Path, lang_hint: Optional[str] = None) -> List[LanguageAdapter]:
    """Return all adapters whose ecosystem is present at root (priority order).
    A --lang hint forces a single adapter."""
    if lang_hint:
        mapping = {"dotnet": DotNetAdapter, "java": JavaAdapter, "node": NodeAdapter}
        cls = mapping.get(lang_hint.lower())
        if cls:
            return [cls()]
        print(f"[WARN] Unknown --lang '{lang_hint}', auto-detecting.", file=sys.stderr)
    # One tree walk for all adapters' markers instead of one walk each —
    # proving an ecosystem absent costs a full walk per adapter otherwise.
    all_names = frozenset().union(*(a.marker_filenames for a in _ADAPTERS))
    all_suffixes = tuple(s for a in _ADAPTERS for s in a.marker_suffixes)
    pending = list(_ADAPTERS)
    found: List[LanguageAdapter] = []
    for f in _iter_files(
        root, filenames=all_names, suffixes=all_suffixes,
        excluded=_NODE_EXCLUDED_DIRS,
    ):
        low = f.name.lower()
        for adapter in list(pending):
            if low in adapter.marker_filenames or (
                adapter.marker_suffixes and low.endswith(adapter.marker_suffixes)
            ):
                pending.remove(adapter)
                found.append(adapter)
        if not pending:
            break
    found.sort(key=_ADAPTERS.index)
    return found or [DotNetAdapter()]  # safe fallback


def detect_adapter(root: Path, lang_hint: Optional[str] = None) -> LanguageAdapter:
    return detect_adapters(root, lang_hint)[0]


def partition_changes(
    changes: List[FileChange],
    adapters: List[LanguageAdapter],
    git_root: Path,
    scope_root: Path,
) -> Dict[str, List[FileChange]]:
    """Route each change to the adapter owning its nearest build-file ancestor.
    Changes with no owning build file go to every adapter (safe fallback —
    each adapter's own UNKNOWN/unmatched escalation then applies)."""
    slices: Dict[str, List[FileChange]] = {a.language: [] for a in adapters}
    for change in changes:
        owner_lang: Optional[str] = None
        d = (git_root / change.path).parent
        while _is_under(d, scope_root):
            for adapter in adapters:
                if adapter.has_build_file(d):
                    owner_lang = adapter.language
                    break
            if owner_lang is not None or d == scope_root:
                break
            d = d.parent
        if owner_lang is not None:
            slices[owner_lang].append(change)
        else:
            for adapter in adapters:
                slices[adapter.language].append(change)
    return slices


# ---------------------------------------------------------------------------
# Core assessment engine
# ---------------------------------------------------------------------------

def _tp(projects: List[Project]) -> List[Project]:
    return [p for p in projects if p.is_test_project]


def _make_run_all(
    changes: List[FileChange],
    projects: List[Project],
    workspace_files: List[Path],
    reason: str,
    notes: List[str],
    language: str,
) -> ImpactResult:
    tp = _tp(projects)
    return ImpactResult(
        changes=changes,
        affected_source_projects=[],
        affected_test_projects=[p.name for p in tp],
        affected_test_classes=set(),
        test_filter="",
        test_project_paths=[str(p.path) for p in tp],
        workspace_files=[str(w) for w in workspace_files],
        run_all=True,
        reason=reason,
        language=language,
        strategy_notes=notes,
    )


def _extract_changed_methods(
    file_abs: Path,
    base_ref: Optional[str],
    use_working_tree: bool,
    git_root: Path,
    method_re: re.Pattern,
) -> List[str]:
    """Return method names that have at least one changed line in file_abs."""
    try:
        rel = str(file_abs.relative_to(git_root))
    except ValueError:
        return []
    effective_base = base_ref if base_ref else "HEAD~1"
    cmd = (
        ["git", "diff", "--unified=0", "--", rel]
        if use_working_tree
        else ["git", "diff", "--unified=0", effective_base, "--", rel]
    )
    try:
        diff_out = subprocess.check_output(
            cmd, cwd=str(git_root), stderr=subprocess.DEVNULL, text=True
        )
    except (subprocess.CalledProcessError, OSError):
        return []

    changed_ranges: List[Tuple[int, int]] = []
    for m in _HUNK_HEADER_RE.finditer(diff_out):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count > 0:
            changed_ranges.append((start, start + count - 1))
    if not changed_ranges:
        return []

    try:
        lines = file_abs.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    method_starts: List[Tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        m = method_re.match(line)
        if m:
            method_starts.append((i, _method_name(m)))
    if not method_starts:
        return []

    line_nos = [ln for ln, _ in method_starts]
    names = [nm for _, nm in method_starts]
    found: Set[str] = set()
    for rng_start, rng_end in changed_ranges:
        # Method whose body contains rng_start
        idx = bisect.bisect_right(line_nos, rng_start) - 1
        if idx >= 0:
            found.add(names[idx])
        # Methods declared inside the changed range (new methods)
        lo = bisect.bisect_left(line_nos, rng_start)
        hi = bisect.bisect_right(line_nos, rng_end)
        for i in range(lo, hi):
            found.add(names[i])
    return sorted(found)


def _find_method_owners(
    lines: List[str],
    method_re: re.Pattern,
) -> Dict[int, Tuple[str, str]]:
    """Map each method's 1-based line number to its (class_name, method_name).

    Uses brace-depth tracking to determine the enclosing class even in files
    with multiple classes (nested or sequential).
    """
    class_stack: List[Tuple[str, int]] = []  # (class_name, depth_at_open_brace)
    depth = 0
    result: Dict[int, Tuple[str, str]] = {}
    for lineno, line in enumerate(lines, 1):
        opens = line.count("{")
        closes = line.count("}")
        # Pop classes whose scope has ended
        depth += opens - closes
        while class_stack and depth <= class_stack[-1][1]:
            class_stack.pop()
        cls_m = _CLASS_DECL_RE.match(line)
        if cls_m:
            # Record depth before opens on this line as the class's outer depth
            class_stack.append((cls_m.group(1), depth - opens))
        meth_m = method_re.match(line)
        if meth_m and class_stack:
            result[lineno] = (class_stack[-1][0], _method_name(meth_m))
    return result


# Annotation / attribute names that mark a runnable test method. Exact names
# only — substring matching would treat @TestOnly helpers as tests and emit
# filters that run nothing.
_TEST_ANNOTATIONS: FrozenSet[str] = frozenset({
    "test", "parameterizedtest", "repeatedtest", "testfactory", "testtemplate",  # JUnit
    "fact", "theory",                                                            # xUnit
    "testmethod", "datatestmethod",                                              # MSTest
    "testcase",                                                                  # NUnit
})

_ANNOTATION_NAME_RE = re.compile(r'[@\[]\s*(?:\w+\.)*(\w+)')


def _is_test_annotated(lines: List[str], decl_lineno: int) -> bool:
    """True if the method declared at decl_lineno (1-based) is preceded by a
    test annotation/attribute (@Test, [Fact], [Theory], @ParameterizedTest, …)."""
    i = decl_lineno - 2
    while i >= 0:
        s = lines[i].strip()
        if not s:
            i -= 1
            continue
        if s.startswith(("@", "[")):
            for name in _ANNOTATION_NAME_RE.findall(s):
                if name.lower() in _TEST_ANNOTATIONS:
                    return True
            i -= 1
            continue
        return False
    return False


def _extract_changed_method_owners(
    file_abs: Path,
    base_ref: Optional[str],
    use_working_tree: bool,
    git_root: Path,
    method_re: re.Pattern,
) -> List[Tuple[str, str, bool]]:
    """Return (class_name, method_name, is_test_annotated) triples for methods
    with at least one changed line."""
    try:
        rel = str(file_abs.relative_to(git_root))
    except ValueError:
        return []
    effective_base = base_ref if base_ref else "HEAD~1"
    cmd = (
        ["git", "diff", "--unified=0", "--", rel]
        if use_working_tree
        else ["git", "diff", "--unified=0", effective_base, "--", rel]
    )
    try:
        diff_out = subprocess.check_output(
            cmd, cwd=str(git_root), stderr=subprocess.DEVNULL, text=True
        )
    except (subprocess.CalledProcessError, OSError):
        return []

    changed_ranges: List[Tuple[int, int]] = []
    for m in _HUNK_HEADER_RE.finditer(diff_out):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count > 0:
            changed_ranges.append((start, start + count - 1))
    if not changed_ranges:
        return []

    try:
        lines = file_abs.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    owners = _find_method_owners(lines, method_re)
    if not owners:
        return []

    line_nos = sorted(owners)
    found: Set[Tuple[str, str, bool]] = set()

    def _add(lineno: int) -> None:
        cls, mth = owners[lineno]
        found.add((cls, mth, _is_test_annotated(lines, lineno)))

    for rng_start, rng_end in changed_ranges:
        idx = bisect.bisect_right(line_nos, rng_start) - 1
        if idx >= 0:
            _add(line_nos[idx])
        lo = bisect.bisect_left(line_nos, rng_start)
        hi = bisect.bisect_right(line_nos, rng_end)
        for i in range(lo, hi):
            _add(line_nos[i])
    return sorted(found)


def _find_test_methods_in_cache(
    source_methods: List[str],
    test_class: str,
    cache: Dict[Path, str],
    method_re: re.Pattern,
) -> List[str]:
    """Return test method names whose names contain any source method name (case-insensitive)."""
    needles = [m.lower() for m in source_methods]
    class_pat = re.compile(r'\bclass\s+' + re.escape(test_class) + r'\b')
    found: List[str] = []
    seen: Set[str] = set()
    for content in cache.values():
        if not class_pat.search(content):
            continue
        for line in content.splitlines():
            m = method_re.match(line)
            if m:
                name = _method_name(m)
                if name in seen:
                    continue
                if any(needle in name.lower() for needle in needles):
                    found.append(name)
                    seen.add(name)
    return found


def _collect_changes(
    base_ref: Optional[str],
    head_ref: str,
    git_root: Path,
    use_working_tree: bool,
    staged_only: bool,
    notes: List[str],
) -> List[FileChange]:
    if staged_only:
        notes.append("Comparing staged changes only")
        return get_changed_files_working_tree(git_root, staged_only=True)
    if use_working_tree:
        notes.append("Comparing against working tree (staged + unstaged)")
        return get_changed_files_working_tree(git_root)
    if base_ref:
        return get_changed_files(base_ref, head_ref, git_root)
    notes.append("No --base provided; defaulting to HEAD~1")
    return get_changed_files("HEAD~1", head_ref, git_root)


def assess(
    root: Path,
    git_root: Path,
    base_ref: Optional[str],
    head_ref: str = "HEAD",
    strategy: str = "hybrid",
    use_working_tree: bool = False,
    staged_only: bool = False,
    adapter: Optional[LanguageAdapter] = None,
    changes: Optional[List[FileChange]] = None,
) -> ImpactResult:
    """Run the full test impact assessment."""
    if adapter is None:
        adapter = detect_adapter(root)

    notes: List[str] = [f"Language adapter: {adapter.language}"]

    # ── 1. Collect changes (unless injected by assess_all) ───────────────
    if changes is None:
        changes = _collect_changes(
            base_ref, head_ref, git_root, use_working_tree, staged_only, notes
        )

    # ── 1b. Scope changes to --root ───────────────────────────────────────
    scope = root.resolve()
    if scope != git_root:
        in_scope = [
            c for c in changes
            if any(_is_under(git_root / p, scope) for p in (c.path, c.old_path))
        ]
        skipped = [c.path for c in changes if c not in in_scope]
        if skipped:
            notes.append(
                f"Ignored {len(skipped)} change(s) outside --root: {skipped}"
            )
        changes = in_scope

    def _finalize(result: ImpactResult) -> ImpactResult:
        result.test_command = adapter.fmt_command(result)
        return result

    # ── 2. Classify ───────────────────────────────────────────────────────
    by_cat: Dict[ChangeCategory, List[FileChange]] = {c: [] for c in ChangeCategory}
    for change in changes:
        by_cat[adapter.classify(change)].append(change)

    infra   = by_cat[ChangeCategory.INFRA]
    source  = by_cat[ChangeCategory.SOURCE]
    config  = by_cat[ChangeCategory.CONFIG]
    unknown = by_cat[ChangeCategory.UNKNOWN]

    # ── 3. Discover projects ──────────────────────────────────────────────
    projects, workspace_files = adapter.discover(root)

    if not changes:
        return _finalize(ImpactResult(
            changes=[], affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            workspace_files=[str(w) for w in workspace_files], run_all=False,
            reason="No changed files detected", language=adapter.language,
            strategy_notes=notes,
        ))

    if not projects:
        return _finalize(ImpactResult(
            changes=changes, affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            workspace_files=[str(w) for w in workspace_files], run_all=True,
            reason="No project files found — cannot analyse, running all tests",
            language=adapter.language, strategy_notes=notes,
        ))

    tp = _tp(projects)
    reverse_deps = build_reverse_deps(projects)

    # ── 4. Infra changes ──────────────────────────────────────────────────
    # Workspace-level infra (.sln, root pom/package.json, settings.gradle,
    # global config) → run everything. Module-level build files (a discovered
    # project's own build file) → scope through the dependency graph like a
    # config change owned by that project.
    module_infra: List[FileChange] = []
    if infra:
        ws_paths = {Path(w).resolve() for w in workspace_files}
        proj_paths = {p.path for p in projects}
        workspace_infra: List[FileChange] = []
        for change in infra:
            file_abs = (git_root / change.path).resolve()
            if file_abs in proj_paths and file_abs not in ws_paths:
                module_infra.append(change)
            else:
                workspace_infra.append(change)
        if workspace_infra:
            notes.append(
                f"Infrastructure files changed: {[c.path for c in workspace_infra]}"
            )
            return _finalize(_make_run_all(
                changes, projects, workspace_files,
                f"Infrastructure file(s) changed — running all {len(tp)} test project(s)",
                notes, adapter.language,
            ))
        notes.append(
            "Module build file(s) changed — scoping to owning project(s): "
            f"{[c.path for c in module_infra]}"
        )
        config = config + module_infra

    # ── 5. Unknown file types → safe fallback ────────────────────────────
    if unknown:
        notes.append(f"Unrecognised file types: {[c.path for c in unknown]}")
        return _finalize(_make_run_all(
            changes, projects, workspace_files,
            "Unrecognised file type — running all tests as safe fallback",
            notes, adapter.language,
        ))

    # ── 6. Only ignored files ─────────────────────────────────────────────
    relevant = source + config
    if not relevant:
        return _finalize(ImpactResult(
            changes=changes, affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            workspace_files=[str(w) for w in workspace_files], run_all=False,
            reason="Only documentation or binary files changed — no tests required",
            language=adapter.language, strategy_notes=notes,
        ))

    # ── 7. Symbol cache ───────────────────────────────────────────────────
    test_file_cache = adapter.build_test_file_cache(tp)

    # ── 8. Process each changed file ─────────────────────────────────────
    affected_test_paths: Set[Path] = set()
    affected_classes: Set[str] = set()
    affected_source_names: Set[str] = set()
    unmatched_source: List[FileChange] = []

    def _handle_source(change: FileChange) -> None:
        found_tests: Set[Path] = set()
        local_classes: Set[str] = set()
        is_test_file_change = False  # True when the changed file lives in a test project

        for analysis_path in change.analysis_paths():
            owner, test_paths = strategy_dependency_graph(
                analysis_path, projects, reverse_deps, git_root
            )
            if owner:
                # is_test_file(): .NET always True; Java uses "src/test/"; Node uses .test./.spec.
                is_test = owner.is_test_project and adapter.is_test_file(analysis_path)
                if is_test:
                    is_test_file_change = True
                    found_tests.add(owner.path)
                    fp = (git_root / change.path).resolve()
                    if fp.exists() and not change.is_deleted:
                        try:
                            content = fp.read_text(encoding="utf-8", errors="replace")
                            test_classes = adapter.extract_test_identifiers(fp, content)
                            m_re = adapter.method_decl_re
                            if m_re:
                                owners = _extract_changed_method_owners(
                                    fp, base_ref, use_working_tree, git_root, m_re
                                )
                                # Keep only owners whose class is a known test class
                                test_class_set = set(test_classes)
                                matched = [
                                    (cls, mth, annotated)
                                    for cls, mth, annotated in owners
                                    if cls in test_class_set
                                ]
                                # Narrow to methods only when every changed
                                # method is an actual test — a changed helper
                                # affects the whole class, and a filter naming
                                # it would run zero tests.
                                if matched and all(a for _, _, a in matched):
                                    for cls, mth, _ in matched:
                                        local_classes.add(f"{cls}.{mth}")
                                else:
                                    local_classes.update(test_classes)
                            else:
                                local_classes.update(test_classes)
                        except OSError:
                            pass
                else:
                    affected_source_names.add(owner.name)
                    found_tests.update(test_paths)

        if not is_test_file_change:
            if strategy in ("convention", "hybrid"):
                for proj_path, cls in adapter.strategy_convention(change, tp):
                    found_tests.add(proj_path)
                    local_classes.add(cls)

            if strategy in ("symbol", "hybrid"):
                for proj_path, cls in adapter.strategy_symbol_search(
                    change, tp, git_root, test_file_cache
                ):
                    found_tests.add(proj_path)
                    local_classes.add(cls)

        # Source method → test method convention: when a source method changes,
        # try to narrow class-level entries to specific test methods by name.
        m_re = adapter.method_decl_re
        if m_re and local_classes and not change.is_deleted and not is_test_file_change:
            fp = (git_root / change.path).resolve()
            if fp.exists():
                src_methods = _extract_changed_methods(
                    fp, base_ref, use_working_tree, git_root, m_re
                )
                if src_methods:
                    refined: Set[str] = set()
                    for cls in local_classes:
                        if "." in cls:
                            refined.add(cls)
                            continue
                        test_meths = _find_test_methods_in_cache(
                            src_methods, cls, test_file_cache, m_re
                        )
                        if test_meths:
                            for mth in test_meths:
                                refined.add(f"{cls}.{mth}")
                        else:
                            refined.add(cls)
                    local_classes = refined

        affected_classes.update(local_classes)

        if found_tests:
            affected_test_paths.update(found_tests)
        else:
            unmatched_source.append(change)

    def _handle_config(change: FileChange) -> None:
        file_abs = (git_root / change.path).resolve()
        owner = _find_owner(projects, file_abs)
        if owner:
            if owner.is_test_project:
                affected_test_paths.add(owner.path)
                affected_test_paths.update(reverse_deps.get(owner.path, set()))
            else:
                affected_source_names.add(owner.name)
                affected_test_paths.update(reverse_deps.get(owner.path, set()))
        else:
            notes.append(
                f"Config file '{change.path}' not owned by any project — "
                "will trigger full test run"
            )
            affected_test_paths.update(p.path for p in tp)

    for change in source:
        _handle_source(change)
    for change in config:
        _handle_config(change)

    # ── 9. Fallback for unmatched source ──────────────────────────────────
    if unmatched_source:
        notes.append(
            f"No tests found for: {[c.path for c in unmatched_source]}. "
            "Running all test projects as safe fallback."
        )
        affected_test_paths = {p.path for p in tp}

    # ── 10. Fallback when source changed but graph found nothing ──────────
    if affected_source_names and not affected_test_paths:
        notes.append(
            f"Source project(s) {sorted(affected_source_names)} changed but no test "
            "projects found in the dependency graph. Running all test projects."
        )
        affected_test_paths = {p.path for p in tp}

    # ── 10b. Module build-file change invalidates class-level narrowing ──
    # A build file can affect every test in its module, so drop any class
    # filter and run the affected test projects in full.
    if module_infra and affected_classes:
        notes.append(
            "Module build file changed — dropping class-level filter, "
            "running affected test projects in full."
        )
        affected_classes = set()

    # ── 11. Fill missing test classes for transitively-affected projects ─
    affected_classes = adapter.fill_missing_test_classes(
        affected_test_paths, affected_classes, projects
    )

    # ── 12. Prefer method-level over class-level when both exist ─────────
    if any("." in c for c in affected_classes):
        covered = {c.rsplit(".", 1)[0] for c in affected_classes if "." in c}
        affected_classes = {c for c in affected_classes if "." in c or c not in covered}

    # ── 13. Build filter ──────────────────────────────────────────────────
    run_all_triggered = (
        bool(tp)
        and adapter.prefer_run_all_when_all_affected()
        and affected_test_paths == {p.path for p in tp}
    )
    test_filter, capped = adapter.build_filter(affected_classes)
    if capped:
        notes.append(
            f"Filter contained >{FILTER_CLASS_LIMIT} tests — dropping filter, "
            "running full affected test projects."
        )
        test_filter = ""
        affected_classes = set()

    path_to_proj: Dict[Path, Project] = {p.path: p for p in projects}
    resolved_tp = [
        path_to_proj[p] for p in sorted(affected_test_paths) if p in path_to_proj
    ]

    return _finalize(ImpactResult(
        changes=changes,
        affected_source_projects=sorted(affected_source_names),
        affected_test_projects=[p.name for p in resolved_tp],
        affected_test_classes=affected_classes,
        test_filter=test_filter,
        test_project_paths=[str(p.path) for p in resolved_tp],
        workspace_files=[str(w) for w in workspace_files],
        run_all=run_all_triggered,
        reason="Analysis complete",
        language=adapter.language,
        strategy_notes=notes,
    ))


# ---------------------------------------------------------------------------
# Multi-adapter orchestration
# ---------------------------------------------------------------------------

def assess_all(
    root: Path,
    git_root: Path,
    base_ref: Optional[str],
    head_ref: str = "HEAD",
    strategy: str = "hybrid",
    use_working_tree: bool = False,
    staged_only: bool = False,
    adapters: Optional[List[LanguageAdapter]] = None,
) -> List[Tuple[LanguageAdapter, ImpactResult]]:
    """Assess once per detected ecosystem. In polyglot repos, changes are
    partitioned by nearest build-file ancestor and each adapter analyses
    only its own slice."""
    if adapters is None:
        adapters = detect_adapters(root)
    if len(adapters) == 1:
        return [(adapters[0], assess(
            root, git_root, base_ref, head_ref, strategy,
            use_working_tree, staged_only, adapters[0],
        ))]

    collect_notes: List[str] = []
    changes = _collect_changes(
        base_ref, head_ref, git_root, use_working_tree, staged_only, collect_notes
    )
    slices = partition_changes(changes, adapters, git_root, root.resolve())
    pairs: List[Tuple[LanguageAdapter, ImpactResult]] = []
    for adapter in adapters:
        adapter_changes = slices.get(adapter.language, [])
        if not adapter_changes:
            continue
        pairs.append((adapter, assess(
            root, git_root, base_ref, head_ref, strategy,
            use_working_tree, staged_only, adapter, changes=adapter_changes,
        )))
    if not pairs:
        pairs = [(adapters[0], assess(
            root, git_root, base_ref, head_ref, strategy,
            use_working_tree, staged_only, adapters[0], changes=[],
        ))]
    return pairs


def _merge_results(results: List[ImpactResult]) -> ImpactResult:
    """Collapse per-language results into one summary result (used by the
    CI formatters, whose output is a flat variable set)."""
    if len(results) == 1:
        return results[0]
    filters = [r.test_filter for r in results if r.test_filter]
    commands = [
        r.test_command for r in results
        if r.test_command and r.test_command != "(no tests to run)"
    ]
    seen_changes: Set[Tuple[str, str]] = set()
    changes: List[FileChange] = []
    for r in results:
        for c in r.changes:
            key = (c.path, c.status.value)
            if key not in seen_changes:
                seen_changes.add(key)
                changes.append(c)
    return ImpactResult(
        changes=changes,
        affected_source_projects=[x for r in results for x in r.affected_source_projects],
        affected_test_projects=[x for r in results for x in r.affected_test_projects],
        affected_test_classes=set().union(*[r.affected_test_classes for r in results]),
        # A single combined filter string is only meaningful for one runner
        test_filter=filters[0] if len(filters) == 1 else "",
        test_project_paths=[x for r in results for x in r.test_project_paths],
        workspace_files=[x for r in results for x in r.workspace_files],
        run_all=any(r.run_all for r in results),
        reason="; ".join(r.reason for r in results),
        language=",".join(r.language for r in results),
        test_command=" && ".join(commands) or "(no tests to run)",
        strategy_notes=[x for r in results for x in r.strategy_notes],
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _fmt_human_one(result: ImpactResult) -> str:
    sep = "─" * 66

    def section(title: str, items) -> List[str]:
        item_list = sorted(items)
        if not item_list:
            return [f"  {title}: (none)"]
        return [f"  {title} ({len(item_list)}):"] + [f"    • {i}" for i in item_list]

    changed_by_status: Dict[str, List[str]] = {}
    for c in result.changes:
        changed_by_status.setdefault(c.status.value, []).append(
            c.path if not c.is_rename else f"{c.old_path} → {c.path}"
        )

    lines: List[str] = [
        sep,
        "  TEST IMPACT ANALYSIS",
        sep,
        f"  Language: {result.language}",
        f"  Status  : {'RUN ALL TESTS' if result.run_all and not result.test_filter else 'Targeted run'}",
        f"  Reason  : {result.reason}",
        sep,
    ]

    for status, paths in sorted(changed_by_status.items()):
        lines += section(f"Changed [{status}]", paths)

    lines += [
        "",
        *section("Affected source projects", result.affected_source_projects),
        "",
        *section("Affected test projects", result.affected_test_projects),
        "",
        *section("Affected test identifiers", result.affected_test_classes),
        "",
        "  test filter:",
        f"    {result.test_filter or '(none — run full test project)'}",
        "",
        "  command:",
        f"    {result.test_command}",
    ]

    if result.strategy_notes:
        lines += ["", "  Notes:"]
        for note in result.strategy_notes:
            lines.append(f"    ! {note}")

    lines.append(sep)
    return "\n".join(lines)


def fmt_human(results: List[ImpactResult]) -> str:
    return "\n".join(_fmt_human_one(r) for r in results)


def _result_dict(result: ImpactResult) -> Dict:
    return {
        "language": result.language,
        "reason": result.reason,
        "run_all": result.run_all,
        "changes": [
            {"path": c.path, "old_path": c.old_path, "status": c.status.value}
            for c in result.changes
        ],
        "affected_source_projects": result.affected_source_projects,
        "affected_test_projects": result.affected_test_projects,
        "affected_test_classes": sorted(result.affected_test_classes),
        "test_filter": result.test_filter,
        "test_project_paths": result.test_project_paths,
        "workspace_files": result.workspace_files,
        "test_command": result.test_command,
        "strategy_notes": result.strategy_notes,
    }


def fmt_json(results: List[ImpactResult]) -> str:
    if len(results) == 1:
        return json.dumps(_result_dict(results[0]), indent=2)
    merged = _result_dict(_merge_results(results))
    merged["results"] = [_result_dict(r) for r in results]
    return json.dumps(merged, indent=2)


def fmt_github_actions(results: List[ImpactResult]) -> str:
    result = _merge_results(results)
    simple = {
        "language": result.language,
        "test_filter": result.test_filter,
        "run_all": str(result.run_all).lower(),
        "has_tests": str(bool(result.test_project_paths or result.run_all)).lower(),
        "test_project_paths": ",".join(result.test_project_paths),
    }
    # shlex.quote ensures values with spaces, quotes, or special chars are safe.
    lines = [f"echo {shlex.quote(f'{k}={v}')} >> $GITHUB_OUTPUT" for k, v in simple.items()]
    cmd = result.test_command
    # Heredoc syntax for multi-line / quote-containing test_command value.
    lines += [
        'printf "test_command<<__GHA_EOF__\\n" >> $GITHUB_OUTPUT',
        f'printf "%s\\n" {shlex.quote(cmd)} >> $GITHUB_OUTPUT',
        'printf "__GHA_EOF__\\n" >> $GITHUB_OUTPUT',
    ]
    return "\n".join(lines)


def _ado_escape(v: str) -> str:
    return v.replace("%", "%AZP25").replace("]", "%5D").replace("\r", "").replace("\n", "")


def fmt_azure_devops(results: List[ImpactResult]) -> str:
    result = _merge_results(results)
    vars_ = {
        "language": result.language,
        "testFilter": result.test_filter,
        "runAllTests": str(result.run_all).lower(),
        "testProjectPaths": ",".join(result.test_project_paths),
        "hasTests": str(bool(result.test_project_paths or result.run_all)).lower(),
        "testCommand": result.test_command,
    }
    return "\n".join(
        f"echo '##vso[task.setvariable variable={k}]{_ado_escape(v)}'"
        for k, v in vars_.items()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assess_impact.py",
        description=(
            "Test Impact Analysis — detect which tests to run based on code changes.\n"
            "Supports: C# / .NET, Java (Maven + Gradle), Node.js (Jest / Vitest)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
language adapters (auto-detected by default):
  dotnet   C# / .NET — project dependency graph via .sln/.csproj
  java     Java / Kotlin — Maven pom.xml and/or Gradle build.gradle
  node     JavaScript / TypeScript — npm/yarn/pnpm + Jest/Vitest

strategies:
  project    Project dependency graph only (fastest, least precise)
  convention Naming convention mapping only
  symbol     Symbol-grep only (public types → test references)
  hybrid     All three combined (default, recommended)

output formats:
  human          Human-readable report (default)
  json           Machine-readable JSON
  github-actions Shell commands to set GitHub Actions step outputs
  azure-devops   Shell commands to set Azure DevOps pipeline variables

examples:
  # .NET
  python assess_impact.py --base HEAD~1 --root sample-app
  python assess_impact.py --base HEAD~1 --root sample-app --run

  # Java (auto-detected from pom.xml / build.gradle)
  python assess_impact.py --base HEAD~1 --root my-java-app
  python assess_impact.py --base HEAD~1 --root my-java-app --lang java

  # Node.js (auto-detected from package.json)
  python assess_impact.py --base HEAD~1 --root my-node-app
  python assess_impact.py --base HEAD~1 --root my-node-app --lang node

  # Universal
  python assess_impact.py --base origin/main --output json
  python assess_impact.py --unstaged --output github-actions
  python assess_impact.py --base HEAD~1 --run -- --no-build
        """,
    )
    parser.add_argument(
        "--base", metavar="REF",
        help="Base git ref to diff against (e.g. HEAD~1, main, origin/main)",
    )
    parser.add_argument(
        "--head", metavar="REF", default="HEAD",
        help="Head git ref (default: HEAD)",
    )
    parser.add_argument(
        "--root", metavar="DIR", default=".",
        help="Directory to search for project files (default: current directory)",
    )
    parser.add_argument(
        "--lang", metavar="LANG",
        help="Language adapter: dotnet | java | node (default: auto-detect)",
    )
    parser.add_argument(
        "--strategy",
        choices=["project", "convention", "symbol", "hybrid"],
        default="hybrid",
        help="Analysis strategy (default: hybrid)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["human", "json", "github-actions", "azure-devops"],
        default="human",
        help="Output format (default: human)",
    )
    parser.add_argument(
        "--run", action="store_true",
        help="Execute the test suite after analysis",
    )
    parser.add_argument(
        "--unstaged", action="store_true",
        help="Analyse working-tree changes (staged + unstaged) instead of a git diff",
    )
    parser.add_argument(
        "--staged", action="store_true",
        help="Analyse only staged (indexed) changes — useful before committing",
    )
    parser.add_argument(
        "extra_args", nargs=argparse.REMAINDER,
        help="Arguments forwarded to the test runner (after --) when --run is used",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[ERROR] Root directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    git_root = get_git_root(root)
    adapters = detect_adapters(root, lang_hint=args.lang)

    pairs = assess_all(
        root=root,
        git_root=git_root,
        base_ref=args.base,
        head_ref=args.head,
        strategy=args.strategy,
        use_working_tree=args.unstaged,
        staged_only=args.staged,
        adapters=adapters,
    )
    results = [result for _, result in pairs]

    formatters = {
        "human": fmt_human,
        "json": fmt_json,
        "github-actions": fmt_github_actions,
        "azure-devops": fmt_azure_devops,
    }
    print(formatters[args.output](results))

    if args.run:
        extra = [a for a in args.extra_args if a != "--"]
        code = 0
        for adapter, result in pairs:
            rc = adapter.run_tests(result, extra, cwd=root)
            if rc != 0:
                code = rc
        sys.exit(code)


if __name__ == "__main__":
    main()
