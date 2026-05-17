#!/usr/bin/env python3
"""
Test Impact Analysis (TIA) — C# / .NET  v2
============================================
Analyses git changes and selects the minimal set of tests to run.

Three layered strategies (all active in "hybrid" mode):
  1. Project dependency graph  — parse .sln/.csproj to find which test projects
                                 reference the changed source project (BFS-transitive)
  2. Convention mapping        — FooService.cs  →  FooServiceTests.cs
  3. Symbol search             — grep public type names from changed files in test code
                                 (test file contents are cached; deleted files handled)

Handles: renamed files (old path analysed), deleted files, config files,
         project-name collisions, obj/bin exclusion, filter length overflow.

Usage:
    python assess_impact.py --base HEAD~1
    python assess_impact.py --base main --output json
    python assess_impact.py --base HEAD~1 --run
    python assess_impact.py --unstaged --output human
    python assess_impact.py --base HEAD~1 --output github-actions
    python assess_impact.py --base HEAD~1 --run -- --no-build --verbosity minimal
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_PACKAGE_NAMES: Set[str] = {
    "xunit", "xunit.core", "xunit.runner.visualstudio",
    "nunit", "nunit3testadapter",
    "mstest.testframework", "mstest.testadapter",
    "microsoft.net.test.sdk",
    "moq", "nsubstitute", "fluentassertions",
    "specflow", "bunit", "shouldly",
    "autofixture", "bogus",
    "coverlet.collector", "coverlet.msbuild",
}

TEST_PROJECT_SUFFIXES: Tuple[str, ...] = (
    ".tests", ".test", ".specs", ".spec",
    "tests", "test", "specs", "spec",
)

# Build-system files — always run the full suite
INFRA_EXTENSIONS: Tuple[str, ...] = (".sln", ".csproj")
INFRA_FILENAMES: Tuple[str, ...] = (
    "global.json",
    "nuget.config",
    "directory.build.props",
    "directory.build.targets",
    "directory.packages.props",
    "directory.packages.lock.json",
    ".globalconfig",
)

# Changes to these file extensions are completely ignored (no tests needed)
IGNORED_EXTENSIONS: Tuple[str, ...] = (
    ".md", ".txt", ".rst",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz",
)

# Changes to these exact filenames (basenames) are also completely ignored.
# Listed separately because os.path.splitext('.gitignore') → ('', '') — they have no extension.
IGNORED_FILENAMES: Tuple[str, ...] = (
    ".gitignore", ".gitattributes", ".gitmodules",
    ".editorconfig",
    "license", "licence", "notice", "authors", "changelog",
)

# Non-code project files — run the owning project's tests (not all tests)
CONFIG_EXTENSIONS: Tuple[str, ...] = (
    ".json", ".xml", ".yaml", ".yml",
    ".config", ".resx", ".resw",
    ".razor", ".cshtml", ".aspx", ".ascx",
    ".proto", ".graphql",
)

# Directories excluded from project discovery
EXCLUDED_DIRS: Tuple[str, ...] = (
    "obj", "bin", ".git", ".vs", ".idea",
    "node_modules", "packages", ".nuget",
)

# Maximum number of test classes in --filter before dropping to project-level (no filter)
FILTER_CLASS_LIMIT = 40


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
    INFRA = auto()       # always run all tests
    IGNORED = auto()     # skip, no tests needed
    CS_SOURCE = auto()   # full 3-strategy analysis
    CONFIG = auto()      # find owning project, run its tests
    UNKNOWN = auto()     # unrecognised — run all tests (safe fallback)


@dataclass
class FileChange:
    path: str            # current path (new path for renames)
    old_path: str        # original path (same as path for non-renames/deletes)
    status: FileStatus

    @property
    def is_deleted(self) -> bool:
        return self.status == FileStatus.DELETED

    @property
    def is_rename(self) -> bool:
        return self.status in (FileStatus.RENAMED, FileStatus.COPIED)

    def analysis_paths(self) -> List[str]:
        """Return all paths worth analysing for this change."""
        if self.is_rename:
            return [self.path, self.old_path]
        return [self.path]


@dataclass
class CSharpProject:
    name: str
    path: Path           # absolute path to .csproj
    is_test_project: bool = False
    project_references: List[str] = field(default_factory=list)  # stem names
    test_packages: Set[str] = field(default_factory=set)

    @property
    def directory(self) -> Path:
        return self.path.parent


@dataclass
class ImpactResult:
    changes: List[FileChange]
    affected_source_projects: List[str]
    affected_test_projects: List[str]
    affected_test_classes: Set[str]
    test_filter: str                   # dotnet test --filter expression
    test_project_paths: List[str]      # absolute .csproj paths to execute
    solution_paths: List[str]          # discovered .sln files (for run-all mode)
    run_all: bool                      # True → targeted selection abandoned
    reason: str
    strategy_notes: List[str] = field(default_factory=list)


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
    """Return the absolute repository root (where git stores paths relative to)."""
    try:
        out = _run_git("rev-parse", "--show-toplevel", cwd=cwd)
        return Path(out.strip()).resolve()
    except subprocess.CalledProcessError:
        return cwd.resolve()


def _parse_name_status(out: str) -> List[FileChange]:
    """
    Parse `git diff --name-status` output.
    Rename lines:   R100<TAB>old/path.cs<TAB>new/path.cs
    All others:     M<TAB>path.cs
    """
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
                path=parts[2].strip(),
                old_path=parts[1].strip(),
                status=status,
            ))
        else:
            p = parts[1].strip()
            changes.append(FileChange(path=p, old_path=p, status=status))

    return changes


def get_changed_files(
    base_ref: str,
    head_ref: str = "HEAD",
    git_root: Optional[Path] = None,
) -> List[FileChange]:
    """
    Return all files changed between two git refs.
    Includes Deleted (D) and Renamed (R) in addition to the usual ACMT.
    Paths in the result are relative to the git repository root.
    """
    try:
        out = _run_git(
            "diff", "--name-status", "--diff-filter=DACMRT",
            base_ref, head_ref,
            cwd=git_root,
        )
        return _parse_name_status(out)
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] git diff failed: {exc.stderr.strip()}", file=sys.stderr)
        return []


def get_changed_files_working_tree(git_root: Optional[Path] = None) -> List[FileChange]:
    """Return files with uncommitted changes (staged and unstaged, deduplicated)."""
    seen: Set[str] = set()
    all_changes: List[FileChange] = []
    for extra in (["--cached"], []):
        try:
            out = _run_git(
                "diff", "--name-status", "--diff-filter=DACMRT",
                *extra,
                cwd=git_root,
            )
            for change in _parse_name_status(out):
                if change.path not in seen:
                    seen.add(change.path)
                    all_changes.append(change)
        except subprocess.CalledProcessError:
            pass
    return all_changes


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

def classify_change(change: FileChange) -> ChangeCategory:
    path_lower = change.path.lower()
    basename = os.path.basename(path_lower)
    ext = os.path.splitext(path_lower)[1]

    if ext in INFRA_EXTENSIONS or basename in INFRA_FILENAMES:
        return ChangeCategory.INFRA

    if ext in IGNORED_EXTENSIONS or basename in IGNORED_FILENAMES:
        return ChangeCategory.IGNORED

    if ext == ".cs":
        return ChangeCategory.CS_SOURCE

    if ext in CONFIG_EXTENSIONS:
        return ChangeCategory.CONFIG

    return ChangeCategory.UNKNOWN


# ---------------------------------------------------------------------------
# C# project discovery
# ---------------------------------------------------------------------------

_SLN_PROJECT_RE = re.compile(
    r'Project\("[^"]*"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+\.csproj)"',
    re.IGNORECASE,
)


def _excluded(path: Path) -> bool:
    """True if the path passes through any excluded directory."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def find_solution_files(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.sln") if not _excluded(p)]


def parse_solution(sln_path: Path) -> Dict[str, Path]:
    """Return {project_name: absolute_csproj_path} from a .sln file."""
    result: Dict[str, Path] = {}
    try:
        content = sln_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return result
    sln_dir = sln_path.parent
    for m in _SLN_PROJECT_RE.finditer(content):
        name = m.group(1).strip()
        rel = m.group(2).strip().replace("\\", os.sep).replace("/", os.sep)
        abs_path = (sln_dir / rel).resolve()
        if abs_path.exists() and not _excluded(abs_path):
            result[name] = abs_path
    return result


def _is_test_by_packages(xml_root) -> Tuple[bool, Set[str]]:
    found: Set[str] = set()
    for pkg in xml_root.iter("PackageReference"):
        include = pkg.get("Include", "").lower().strip()
        if include in TEST_PACKAGE_NAMES:
            found.add(include)
    return bool(found), found


def _parse_csproj(name: str, csproj_path: Path) -> CSharpProject:
    project = CSharpProject(name=name, path=csproj_path)

    if name.lower().endswith(TEST_PROJECT_SUFFIXES):
        project.is_test_project = True

    try:
        tree = ET.parse(csproj_path)
        xml_root = tree.getroot()

        for elem in xml_root.iter("IsTestProject"):
            if elem.text and elem.text.strip().lower() == "true":
                project.is_test_project = True

        for ref in xml_root.iter("ProjectReference"):
            include = ref.get("Include", "")
            ref_stem = Path(include.replace("\\", "/")).stem
            if ref_stem and ref_stem not in project.project_references:
                project.project_references.append(ref_stem)

        is_test, pkgs = _is_test_by_packages(xml_root)
        if is_test:
            project.is_test_project = True
            project.test_packages = pkgs

    except (ET.ParseError, OSError):
        pass

    return project


def discover_projects(root: Path) -> List[CSharpProject]:
    """
    Discover all .csproj files under root.

    - Always merges: solution-listed projects + glob results (neither is a fallback).
    - Excludes obj/, bin/, and other build-output directories.
    - Deduplicates by resolved path, so a project appearing in both a solution and
      the glob is only parsed once.
    - When two distinct projects share the same stem name the collision is recorded
      in strategy_notes; both projects are kept and the dependency graph resolves
      references by stem-name-to-multiple-projects correctly.
    """
    # resolved_path → (name_from_solution_or_stem)
    path_to_name: Dict[Path, str] = {}

    for sln in find_solution_files(root):
        for name, path in parse_solution(sln).items():
            path_to_name.setdefault(path, name)

    for csproj in root.rglob("*.csproj"):
        resolved = csproj.resolve()
        if not _excluded(resolved):
            path_to_name.setdefault(resolved, resolved.stem)

    return [_parse_csproj(name, path) for path, name in path_to_name.items()]


# ---------------------------------------------------------------------------
# Helpers that work on List[CSharpProject]
# ---------------------------------------------------------------------------

def _test_projects(projects: List[CSharpProject]) -> List[CSharpProject]:
    return [p for p in projects if p.is_test_project]


def _source_projects(projects: List[CSharpProject]) -> List[CSharpProject]:
    return [p for p in projects if not p.is_test_project]


def _find_by_stem(projects: List[CSharpProject], stem: str) -> List[CSharpProject]:
    """Return all projects whose .csproj stem matches (case-insensitive)."""
    stem_lower = stem.lower()
    return [p for p in projects if p.path.stem.lower() == stem_lower]


def _find_owner(projects: List[CSharpProject], file_abs: Path) -> Optional[CSharpProject]:
    """Return the most specific project that contains file_abs."""
    best: Optional[CSharpProject] = None
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


# ---------------------------------------------------------------------------
# Dependency graph (BFS-transitive)
# ---------------------------------------------------------------------------

def build_reverse_deps(projects: List[CSharpProject]) -> Dict[Path, Set[Path]]:
    """
    Return {source_project_path: set_of_test_project_paths_to_run_when_it_changes}.

    Uses BFS to propagate transitively:
      if SourceB depends on SourceA, and TestB tests SourceB,
      then when SourceA changes → TestB should also run.
    """
    all_paths = [p.path for p in projects]

    # direct[path] = set of test project paths that directly reference this project
    direct: Dict[Path, Set[Path]] = {p.path: set() for p in projects}
    for proj in projects:
        if not proj.is_test_project:
            continue
        for ref_stem in proj.project_references:
            for ref_proj in _find_by_stem(projects, ref_stem):
                direct[ref_proj.path].add(proj.path)

    # dependents[path] = source projects that directly depend on this project
    # (used for transitive fan-out: if X changes, who might be affected?)
    dependents: Dict[Path, Set[Path]] = {p.path: set() for p in projects}
    for proj in projects:
        if proj.is_test_project:
            continue
        for ref_stem in proj.project_references:
            for ref_proj in _find_by_stem(projects, ref_stem):
                dependents[ref_proj.path].add(proj.path)

    # BFS: for each source S, walk all projects that (transitively) depend on S,
    # and collect their test coverage.
    result: Dict[Path, Set[Path]] = {path: set(testers) for path, testers in direct.items()}
    for source_path in all_paths:
        visited: Set[Path] = {source_path}
        queue: List[Path] = list(dependents.get(source_path, set()))
        while queue:
            dep_path = queue.pop(0)
            if dep_path in visited:
                continue
            visited.add(dep_path)
            result[source_path].update(direct.get(dep_path, set()))
            queue.extend(dependents.get(dep_path, set()) - visited)

    return result


# ---------------------------------------------------------------------------
# Strategy 1 — Project dependency graph
# ---------------------------------------------------------------------------

def strategy_dependency_graph(
    file_path: str,
    projects: List[CSharpProject],
    reverse_deps: Dict[Path, Set[Path]],
    git_root: Path,
) -> Tuple[Optional[CSharpProject], Set[Path]]:
    """
    Returns (owning_project, set_of_test_project_paths).
    Returns (None, empty) if the file doesn't map to any project.
    """
    file_abs = (git_root / file_path).resolve()
    owner = _find_owner(projects, file_abs)
    if not owner:
        return None, set()

    if owner.is_test_project:
        return owner, {owner.path}

    return owner, reverse_deps.get(owner.path, set())


# ---------------------------------------------------------------------------
# Strategy 2 — Convention-based test class mapping
# ---------------------------------------------------------------------------

def strategy_convention(
    change: FileChange,
    test_projects: List[CSharpProject],
) -> List[Tuple[Path, str]]:
    """
    Map FooService.cs → FooServiceTests.cs (and variants).
    Analyses both new and old paths (handles renames: the old test may still exist).
    Only applies to .cs files.
    Returns [(test_project_path, test_class_name), ...].
    """
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
        for proj in test_projects:
            for candidate in candidates:
                if list(proj.directory.rglob(f"{candidate}.cs")):
                    key = (proj.path, candidate)
                    if key not in seen:
                        seen.add(key)
                        results.append(key)

    return results


# ---------------------------------------------------------------------------
# Strategy 3 — Symbol search (with file-content cache)
# ---------------------------------------------------------------------------

_TYPE_DECL_RE = re.compile(
    r'\b(?:public|internal)\s+'
    r'(?:(?:abstract|sealed|static|partial|readonly|new)\s+)*'
    r'(?:class|interface|enum|struct|record)\s+(\w+)',
)

_TEST_CLASS_RE = re.compile(r'\bclass\s+(\w+)')


def build_test_file_cache(test_projects: List[CSharpProject]) -> Dict[Path, str]:
    """Pre-load every test .cs file once, shared across all symbol searches."""
    cache: Dict[Path, str] = {}
    for proj in test_projects:
        for cs_file in proj.directory.rglob("*.cs"):
            if cs_file not in cache:
                try:
                    cache[cs_file] = cs_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
    return cache


def strategy_symbol_search(
    change: FileChange,
    test_projects: List[CSharpProject],
    git_root: Path,
    cache: Dict[Path, str],
    max_symbols: int = 20,
) -> List[Tuple[Path, str]]:
    """
    Extract public type names declared in the changed source file, then scan
    cached test-file content for references to those names.
    Skips deleted files (no content to extract symbols from).
    Returns [(test_project_path, test_class_name), ...].
    """
    if change.is_deleted:
        return []

    file_abs = (git_root / change.path).resolve()
    if not file_abs.exists() or file_abs.suffix.lower() != ".cs":
        return []

    try:
        source = file_abs.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    symbols = list(dict.fromkeys(_TYPE_DECL_RE.findall(source)))[:max_symbols]
    if not symbols:
        return []

    patterns = [re.compile(r'\b' + re.escape(sym) + r'\b') for sym in symbols]

    # Build a fast per-project file list for cache lookups
    proj_files: Dict[Path, List[Path]] = {
        proj.path: [f for f in cache if _is_under(f, proj.directory)]
        for proj in test_projects
    }

    seen: Set[Tuple[Path, str]] = set()
    results: List[Tuple[Path, str]] = []

    for proj in test_projects:
        for cs_file in proj_files[proj.path]:
            content = cache[cs_file]
            for pattern in patterns:
                if pattern.search(content):
                    m = _TEST_CLASS_RE.search(content)
                    test_class = m.group(1) if m else cs_file.stem
                    key = (proj.path, test_class)
                    if key not in seen:
                        seen.add(key)
                        results.append(key)
                    break  # one matching symbol per test file is enough

    return results


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Filter builder (with length cap)
# ---------------------------------------------------------------------------

def build_filter(test_classes: Set[str]) -> Tuple[str, bool]:
    """
    Build a dotnet test --filter expression.
    Returns (filter_string, capped) where capped=True means the class count
    exceeded FILTER_CLASS_LIMIT and the filter was dropped (run full project).
    """
    if not test_classes:
        return "", False
    if len(test_classes) > FILTER_CLASS_LIMIT:
        return "", True
    parts = [f"FullyQualifiedName~{cls}" for cls in sorted(test_classes)]
    return "|".join(parts), False


# ---------------------------------------------------------------------------
# Core assessment engine
# ---------------------------------------------------------------------------

def _make_run_all(
    changes: List[FileChange],
    projects: List[CSharpProject],
    slns: List[Path],
    reason: str,
    notes: List[str],
) -> ImpactResult:
    tp = _test_projects(projects)
    return ImpactResult(
        changes=changes,
        affected_source_projects=[],
        affected_test_projects=[p.name for p in tp],
        affected_test_classes=set(),
        test_filter="",
        test_project_paths=[str(p.path) for p in tp],
        solution_paths=[str(s) for s in slns],
        run_all=True,
        reason=reason,
        strategy_notes=notes,
    )


def assess(
    root: Path,
    git_root: Path,
    base_ref: Optional[str],
    head_ref: str = "HEAD",
    strategy: str = "hybrid",
    use_working_tree: bool = False,
) -> ImpactResult:
    """Run the full test impact assessment."""
    notes: List[str] = []

    # ── 1. Collect changed files ──────────────────────────────────────────
    if use_working_tree:
        changes = get_changed_files_working_tree(git_root)
        notes.append("Comparing against working tree (staged + unstaged)")
    elif base_ref:
        changes = get_changed_files(base_ref, head_ref, git_root)
    else:
        changes = get_changed_files("HEAD~1", head_ref, git_root)
        notes.append("No --base provided; defaulting to HEAD~1")

    slns = find_solution_files(root)

    if not changes:
        return ImpactResult(
            changes=[], affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            solution_paths=[str(s) for s in slns], run_all=False,
            reason="No changed files detected", strategy_notes=notes,
        )

    # ── 2. Classify changes ───────────────────────────────────────────────
    by_category: Dict[ChangeCategory, List[FileChange]] = {c: [] for c in ChangeCategory}
    for change in changes:
        by_category[classify_change(change)].append(change)

    infra    = by_category[ChangeCategory.INFRA]
    cs_files = by_category[ChangeCategory.CS_SOURCE]
    config   = by_category[ChangeCategory.CONFIG]
    unknown  = by_category[ChangeCategory.UNKNOWN]
    # IGNORED discarded intentionally

    # ── 3. Discover projects ──────────────────────────────────────────────
    projects = discover_projects(root)
    if not projects:
        return ImpactResult(
            changes=changes, affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            solution_paths=[str(s) for s in slns], run_all=True,
            reason="No .csproj files found — cannot analyse, running all tests",
            strategy_notes=notes,
        )

    tp = _test_projects(projects)
    reverse_deps = build_reverse_deps(projects)

    # ── 4. Infra changes → run everything ────────────────────────────────
    if infra:
        notes.append(f"Infrastructure files changed: {[c.path for c in infra]}")
        return _make_run_all(changes, projects, slns,
            f"Infrastructure file(s) changed — running all {len(tp)} test project(s)", notes)

    # ── 5. Unknown file types → run everything (safe fallback) ───────────
    if unknown:
        notes.append(f"Unrecognised file types changed: {[c.path for c in unknown]}")
        return _make_run_all(changes, projects, slns,
            "Unrecognised file type changed — running all tests as safe fallback", notes)

    # ── 6. Only ignored files changed ────────────────────────────────────
    relevant = cs_files + config
    if not relevant:
        return ImpactResult(
            changes=changes, affected_source_projects=[], affected_test_projects=[],
            affected_test_classes=set(), test_filter="", test_project_paths=[],
            solution_paths=[str(s) for s in slns], run_all=False,
            reason="Only documentation or binary files changed — no tests required",
            strategy_notes=notes,
        )

    # ── 7. Build symbol search cache ──────────────────────────────────────
    test_file_cache = build_test_file_cache(tp)

    # ── 8. Process each changed file ─────────────────────────────────────
    affected_test_paths: Set[Path] = set()
    affected_classes: Set[str] = set()
    affected_source_names: Set[str] = set()
    unmatched_cs: List[FileChange] = []

    def _handle_cs(change: FileChange) -> None:
        found_tests: Set[Path] = set()

        for analysis_path in change.analysis_paths():
            # Strategy 1: project dependency graph
            owner, test_paths = strategy_dependency_graph(
                analysis_path, projects, reverse_deps, git_root
            )
            if owner:
                if owner.is_test_project:
                    found_tests.add(owner.path)
                    # If the test file still exists, extract its class names
                    fp = (git_root / change.path).resolve()
                    if fp.exists():
                        try:
                            content = fp.read_text(encoding="utf-8", errors="replace")
                            for m in _TEST_CLASS_RE.finditer(content):
                                affected_classes.add(m.group(1))
                        except OSError:
                            pass
                else:
                    affected_source_names.add(owner.name)
                    found_tests.update(test_paths)

        # Strategy 2: convention mapping (both new & old paths for renames)
        if strategy in ("convention", "hybrid"):
            for proj_path, cls in strategy_convention(change, tp):
                found_tests.add(proj_path)
                affected_classes.add(cls)

        # Strategy 3: symbol search (skips deleted files automatically)
        if strategy in ("symbol", "hybrid"):
            for proj_path, cls in strategy_symbol_search(
                change, tp, git_root, test_file_cache
            ):
                found_tests.add(proj_path)
                affected_classes.add(cls)

        if found_tests:
            affected_test_paths.update(found_tests)
        else:
            unmatched_cs.append(change)

    def _handle_config(change: FileChange) -> None:
        # Find the owning project; run its test projects.
        # If no project owns this config file, it's treated as UNKNOWN (run all).
        file_abs = (git_root / change.path).resolve()
        owner = _find_owner(projects, file_abs)
        if owner:
            if owner.is_test_project:
                affected_test_paths.add(owner.path)
            else:
                affected_source_names.add(owner.name)
                affected_test_paths.update(reverse_deps.get(owner.path, set()))
        else:
            # Config file outside any known project — conservatively run all
            notes.append(
                f"Config file '{change.path}' not owned by any project — "
                "will trigger full test run"
            )
            affected_test_paths.update(p.path for p in tp)

    for change in cs_files:
        _handle_cs(change)

    for change in config:
        _handle_config(change)

    # ── 9. Fallback for unmatched .cs source files ────────────────────────
    if unmatched_cs:
        notes.append(
            f"No tests found for: {[c.path for c in unmatched_cs]}. "
            "Running all test projects as safe fallback."
        )
        affected_test_paths = {p.path for p in tp}

    # ── 10. Fallback when source changed but dependency graph found nothing ─
    if affected_source_names and not affected_test_paths:
        notes.append(
            f"Source project(s) {sorted(affected_source_names)} changed but no test "
            "projects found in the dependency graph. Running all test projects."
        )
        affected_test_paths = {p.path for p in tp}

    # ── 11. Build filter (with length cap) ────────────────────────────────
    run_all_triggered = affected_test_paths == {p.path for p in tp}
    test_filter, capped = build_filter(affected_classes)
    if capped:
        notes.append(
            f"Filter contained >{FILTER_CLASS_LIMIT} classes — dropping class filter, "
            "running full affected test projects."
        )
        test_filter = ""

    # Resolve test project paths from the collected Path set
    path_to_proj: Dict[Path, CSharpProject] = {p.path: p for p in projects}
    resolved_test_projs = [
        path_to_proj[p] for p in sorted(affected_test_paths) if p in path_to_proj
    ]

    return ImpactResult(
        changes=changes,
        affected_source_projects=sorted(affected_source_names),
        affected_test_projects=[p.name for p in resolved_test_projs],
        affected_test_classes=affected_classes,
        test_filter=test_filter,
        test_project_paths=[str(p.path) for p in resolved_test_projs],
        solution_paths=[str(s) for s in slns],
        run_all=run_all_triggered,
        reason="Analysis complete",
        strategy_notes=notes,
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_dotnet_tests(
    result: ImpactResult,
    extra_args: List[str],
    cwd: Optional[Path] = None,
) -> int:
    """Execute dotnet test using the impact analysis result. Returns exit code."""
    filter_args = ["--filter", result.test_filter] if result.test_filter else []

    if result.run_all:
        # Prefer running via solution files if available; fall back to bare dotnet test
        if result.solution_paths:
            exit_code = 0
            for sln in result.solution_paths:
                cmd = ["dotnet", "test", sln, *extra_args]
                print(f"\n[RUN] {' '.join(cmd)}\n")
                rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
                if rc != 0:
                    exit_code = rc
            return exit_code
        else:
            cmd = ["dotnet", "test", *extra_args]
            print(f"\n[RUN] {' '.join(cmd)}\n")
            return subprocess.call(cmd, cwd=str(cwd) if cwd else None)

    if not result.test_project_paths:
        print("[INFO] No tests to run.", file=sys.stderr)
        return 0

    exit_code = 0
    for proj_path in result.test_project_paths:
        cmd = ["dotnet", "test", proj_path, *extra_args, *filter_args]
        print(f"\n[RUN] {' '.join(cmd)}\n")
        rc = subprocess.call(cmd, cwd=str(cwd) if cwd else None)
        if rc != 0:
            exit_code = rc

    return exit_code


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _dotnet_cmd_oneline(result: ImpactResult) -> str:
    """Always single-line — safe for GitHub Actions / Azure DevOps output."""
    filter_part = f' --filter "{result.test_filter}"' if result.test_filter else ""
    if result.run_all:
        if result.solution_paths:
            return " && ".join(f'dotnet test "{s}"' for s in result.solution_paths)
        return "dotnet test"
    if not result.test_project_paths:
        return "(no tests to run)"
    parts = [f'dotnet test "{p}"{filter_part}' for p in result.test_project_paths]
    return " && ".join(parts)


def _dotnet_cmd_readable(result: ImpactResult) -> str:
    """Multi-line version for human-readable output."""
    return _dotnet_cmd_oneline(result).replace(" && ", " && \\\n    ")


def fmt_human(result: ImpactResult) -> str:
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
        f"  Status  : {'RUN ALL TESTS' if result.run_all else 'Targeted run'}",
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
        *section("Affected test classes", result.affected_test_classes),
        "",
        "  dotnet test filter:",
        f"    {result.test_filter or '(none — run full test project)'}",
        "",
        "  dotnet command:",
        f"    {_dotnet_cmd_readable(result)}",
    ]

    if result.strategy_notes:
        lines += ["", "  Notes:"]
        for note in result.strategy_notes:
            lines.append(f"    ! {note}")

    lines.append(sep)
    return "\n".join(lines)


def fmt_json(result: ImpactResult) -> str:
    return json.dumps(
        {
            "reason": result.reason,
            "run_all": result.run_all,
            "changes": [
                {
                    "path": c.path,
                    "old_path": c.old_path,
                    "status": c.status.value,
                }
                for c in result.changes
            ],
            "affected_source_projects": result.affected_source_projects,
            "affected_test_projects": result.affected_test_projects,
            "affected_test_classes": sorted(result.affected_test_classes),
            "test_filter": result.test_filter,
            "test_project_paths": result.test_project_paths,
            "solution_paths": result.solution_paths,
            "dotnet_command": _dotnet_cmd_oneline(result),
            "strategy_notes": result.strategy_notes,
        },
        indent=2,
    )


def fmt_github_actions(result: ImpactResult) -> str:
    """
    Emit GitHub Actions step-output commands.
    Multiline values use the heredoc form to avoid breaking the shell.
    Reference in subsequent steps as ${{ steps.<id>.outputs.<name> }}.
    """
    cmd = _dotnet_cmd_oneline(result)
    # Simple values — single-line echo
    simple = {
        "test_filter": result.test_filter,
        "run_all": str(result.run_all).lower(),
        "has_tests": str(bool(result.test_project_paths or result.run_all)).lower(),
        "test_project_paths": ",".join(result.test_project_paths),
    }
    lines = [f'echo "{k}={v}" >> $GITHUB_OUTPUT' for k, v in simple.items()]
    # dotnet_command uses heredoc (may contain quotes/spaces)
    lines += [
        'echo "dotnet_command<<__GHA_EOF__" >> $GITHUB_OUTPUT',
        f'echo "{cmd}" >> $GITHUB_OUTPUT',
        'echo "__GHA_EOF__" >> $GITHUB_OUTPUT',
    ]
    return "\n".join(lines)


def fmt_azure_devops(result: ImpactResult) -> str:
    """Emit Azure DevOps pipeline variable setter commands."""
    vars_ = {
        "testFilter": result.test_filter,
        "runAllTests": str(result.run_all).lower(),
        "testProjectPaths": ",".join(result.test_project_paths),
        "hasTests": str(bool(result.test_project_paths or result.run_all)).lower(),
        "dotnetCommand": _dotnet_cmd_oneline(result),
    }
    return "\n".join(
        f"echo '##vso[task.setvariable variable={k}]{v}'" for k, v in vars_.items()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assess_impact.py",
        description="Test Impact Analysis for C# — detect which tests to run based on code changes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
strategies:
  project    Project dependency graph only (fastest, least precise)
  convention Naming convention mapping only (FooService → FooServiceTests)
  symbol     Symbol-grep search only (public types from changed file → test refs)
  hybrid     All three combined (default, recommended)

output formats:
  human          Human-readable report (default)
  json           Machine-readable JSON
  github-actions Shell commands to set GitHub Actions step outputs
  azure-devops   Shell commands to set Azure DevOps pipeline variables

examples:
  python assess_impact.py --base HEAD~1
  python assess_impact.py --base origin/main --head feature/my-branch
  python assess_impact.py --base HEAD~1 --output json
  python assess_impact.py --base HEAD~1 --run
  python assess_impact.py --unstaged --output human
  python assess_impact.py --base HEAD~1 --output github-actions
  python assess_impact.py --base HEAD~1 --run -- --no-build --verbosity minimal

notes:
  • Deleted and renamed files are fully analysed (old path used for convention/graph).
  • Config files (.json, .yaml, etc.) trigger tests for their owning project only.
  • Unknown file types (not .cs, not config, not docs) always trigger a full test run.
  • When > 40 test classes match, the class filter is dropped (full project runs).
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
        help="Directory to search for .sln/.csproj files (default: current directory)",
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
        help="Execute dotnet test after analysis",
    )
    parser.add_argument(
        "--unstaged", action="store_true",
        help="Analyse working-tree changes (staged + unstaged) instead of a git diff",
    )
    parser.add_argument(
        "extra_dotnet_args", nargs=argparse.REMAINDER,
        help="Arguments forwarded to dotnet test (after --) when --run is used",
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

    result = assess(
        root=root,
        git_root=git_root,
        base_ref=args.base,
        head_ref=args.head,
        strategy=args.strategy,
        use_working_tree=args.unstaged,
    )

    formatters = {
        "human": fmt_human,
        "json": fmt_json,
        "github-actions": fmt_github_actions,
        "azure-devops": fmt_azure_devops,
    }
    print(formatters[args.output](result))

    if args.run:
        extra = [a for a in args.extra_dotnet_args if a != "--"]
        sys.exit(run_dotnet_tests(result, extra, cwd=root))


if __name__ == "__main__":
    main()
