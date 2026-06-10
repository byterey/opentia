#!/usr/bin/env python3
"""Self-test: TIA scenarios against multi-app."""

import json, subprocess, sys
from pathlib import Path

REPO   = Path(__file__).parent
APP    = REPO / "multi-app"
SCRIPT = REPO / "assess_impact.py"

PASS = FAIL = 0


def _stash() -> bool:
    r = subprocess.run(["git", "stash", "--include-untracked", "-m", "tia-selftest"], cwd=str(REPO), capture_output=True, text=True)
    return "No local changes" not in r.stdout


def _stash_pop():
    subprocess.run(["git", "stash", "pop"], cwd=str(REPO), capture_output=True)


_stashed = _stash()


def tia(extra_args=(), root=None):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--unstaged", "--root", str(root or APP), "--output", "json", *extra_args],
        capture_output=True, text=True, cwd=str(REPO),
    )
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"_raw": r.stdout + r.stderr}


def check(label, result, *, expect_projects=None, run_all=None, exact=False, no_tests=False, expect_no_filter=False):
    global PASS, FAIL
    actual = set(result.get("affected_test_projects", []))
    ok = True

    if no_tests:
        ok = not actual and not result.get("run_all")
    elif run_all is not None:
        ok = result.get("run_all") == run_all
    elif expect_projects is not None:
        expected = set(expect_projects)
        ok = (actual == expected) if exact else expected.issubset(actual)

    if ok and expect_no_filter and result.get("test_filter"):
        ok = False

    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1

    print(f"  [{status}] {label}")
    if not ok:
        print(f"         expected_projects : {sorted(expect_projects or [])}")
        print(f"         actual_projects   : {sorted(actual)}")
        print(f"         run_all           : {result.get('run_all')}")
        print(f"         reason            : {result.get('reason', '')[:120]}")


def patch(path: Path, text="\n// tia-test\n"):
    orig = path.read_text(encoding="utf-8")
    path.write_text(orig + text, encoding="utf-8")
    return orig


def restore(path: Path, orig: str):
    path.write_text(orig, encoding="utf-8")


def git_add(path: Path):
    subprocess.run(["git", "add", str(path)], cwd=str(REPO), check=True, capture_output=True)


def git_rm_cached(path: Path):
    subprocess.run(["git", "rm", "--cached", str(path)], cwd=str(REPO), check=True, capture_output=True)


# ── helpers ───────────────────────────────────────────────────────────────────
ALL4  = ["MultiApp.Domain.Tests", "MultiApp.Application.Tests",
         "MultiApp.Infrastructure.Tests", "MultiApp.Batch.Tests"]
APP_BATCH   = ["MultiApp.Application.Tests", "MultiApp.Batch.Tests"]
# Application.Tests directly references Infrastructure (uses InMemoryOrderRepository concretely)
INFRA_BATCH = ["MultiApp.Infrastructure.Tests", "MultiApp.Application.Tests", "MultiApp.Batch.Tests"]


def scenario(label, file: Path, *, expect_projects, run_all=None, exact=True, staged=False):
    orig = patch(file)
    if staged:
        git_add(file)
    try:
        result = tia()
        check(label, result, expect_projects=expect_projects, run_all=run_all, exact=exact)
    finally:
        restore(file, orig)
        if staged:
            subprocess.run(["git", "checkout", "--", str(file)], cwd=str(REPO), capture_output=True)


# ─────────────────────────────────────────────────────────────────────────────
print("\n── Layer source changes ──────────────────────────────────────────────")

scenario(
    "Domain entity change  → all 4 test projects",
    APP / "src/MultiApp.Domain/Entities/Order.cs",
    expect_projects=ALL4,
)
scenario(
    "Domain service change → all 4 test projects",
    APP / "src/MultiApp.Domain/Services/OrderDomainService.cs",
    expect_projects=ALL4,
)
scenario(
    "Application service   → Application.Tests + Batch.Tests",
    APP / "src/MultiApp.Application/Services/OrderService.cs",
    expect_projects=APP_BATCH,
)
scenario(
    "Infrastructure repo   → Infrastructure.Tests + Batch.Tests",
    APP / "src/MultiApp.Infrastructure/Repositories/InMemoryOrderRepository.cs",
    expect_projects=INFRA_BATCH,
)
scenario(
    "Batch job change      → Batch.Tests only",
    APP / "src/MultiApp.Batch/Jobs/OrderExpiryJob.cs",
    expect_projects=["MultiApp.Batch.Tests"],
)

print("\n── Infrastructure (INFRA category) ───────────────────────────────────")

csproj = APP / "src/MultiApp.Domain/MultiApp.Domain.csproj"
orig = patch(csproj, "\n<!-- tia-test -->")
result = tia()
check(".csproj change (Domain, base layer) → run_all", result, run_all=True)
restore(csproj, orig)

# Module-level build file on a leaf project → scoped via dependency graph, not run-all
csproj_leaf = APP / "src/MultiApp.Batch/MultiApp.Batch.csproj"
orig = patch(csproj_leaf, "\n<!-- tia-test -->")
result = tia()
check("Leaf .csproj change → Batch.Tests only (module-scoped)", result,
      expect_projects=["MultiApp.Batch.Tests"], exact=True)
restore(csproj_leaf, orig)

# Module build file + source file in same module → full module run, no class
# narrowing (a build-file change can affect every test in the module)
csproj_leaf = APP / "src/MultiApp.Batch/MultiApp.Batch.csproj"
src_leaf = APP / "src/MultiApp.Batch/Jobs/OrderExpiryJob.cs"
o1 = patch(csproj_leaf, "\n<!-- tia-test -->")
o2 = patch(src_leaf)
result = tia()
check("Leaf .csproj + source change → Batch.Tests, no class filter", result,
      expect_projects=["MultiApp.Batch.Tests"], exact=True, expect_no_filter=True)
restore(csproj_leaf, o1)
restore(src_leaf, o2)

# Workspace-level build file → always run-all
sln = APP / "MultiApp.sln"
orig = patch(sln, "\n# tia-test")
result = tia()
check(".sln change → run_all", result, run_all=True)
restore(sln, orig)

print("\n── Root scoping ──────────────────────────────────────────────────────")

# A change outside --root must not trigger this app's tests
outside = REPO / "sample-app/src/SampleApp.Core/Utilities/StringHelper.cs"
orig = patch(outside)
result = tia()
check("Change outside --root → no tests", result, no_tests=True)
restore(outside, orig)

print("\n── Excluded-dir pruning ──────────────────────────────────────────────")

# Generated .cs files under obj/ must not pollute the symbol-search cache
polluted = APP / "tests/MultiApp.Domain.Tests/obj/PollutedTests.cs"
polluted.parent.mkdir(parents=True, exist_ok=True)
polluted.write_text(
    "public class PollutedTests { /* OrderDomainService */ }", encoding="utf-8"
)
src = APP / "src/MultiApp.Domain/Services/OrderDomainService.cs"
orig = patch(src)
try:
    result = tia()
    ids = set(result.get("affected_test_classes", []))
    ok = "PollutedTests" not in {i.split(".")[0] for i in ids}
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] obj/ .cs file excluded from symbol cache")
    if not ok:
        print(f"         identifiers: {sorted(ids)}")
finally:
    restore(src, orig)
    polluted.unlink(missing_ok=True)
    polluted.parent.rmdir()

print("\n── Test file changes ─────────────────────────────────────────────────")

scenario(
    "Domain test file      → Domain.Tests only",
    APP / "tests/MultiApp.Domain.Tests/OrderTests.cs",
    expect_projects=["MultiApp.Domain.Tests"],
)
scenario(
    "Batch test file       → Batch.Tests only",
    APP / "tests/MultiApp.Batch.Tests/OrderExpiryJobTests.cs",
    expect_projects=["MultiApp.Batch.Tests"],
)

print("\n── Config / unknown file types ───────────────────────────────────────")

# config: .json in Application project directory
cfg = APP / "src/MultiApp.Application/appsettings.json"
cfg.write_text('{ "key": "value" }', encoding="utf-8")
git_add(cfg)
try:
    result = tia()
    check("Config .json (Application) → Application.Tests or run_all", result,
          expect_projects=["MultiApp.Application.Tests"], exact=False)
finally:
    git_rm_cached(cfg)
    cfg.unlink(missing_ok=True)

# unknown extension → safe run_all fallback
unk = APP / "src/MultiApp.Domain/readme.xyz"
unk.write_text("unknown", encoding="utf-8")
git_add(unk)
try:
    result = tia()
    check("Unknown file type (.xyz) → run_all", result, run_all=True)
finally:
    git_rm_cached(unk)
    unk.unlink(missing_ok=True)

print("\n── Polyglot (java-fullstack-app: Maven + Angular) ────────────────────")

FS = REPO / "java-fullstack-app"
fs_ts = FS / "frontend/src/app/order-list/order-list.component.ts"
fs_java = FS / "backend/src/main/java/com/example/backend/controller/OrderController.java"

orig = patch(fs_ts)
try:
    result = tia(root=FS)
    check("Frontend .ts change → frontend specs only", result,
          expect_projects=["frontend"], exact=True)
finally:
    restore(fs_ts, orig)

orig = patch(fs_java)
try:
    result = tia(root=FS)
    check("Backend .java change → backend tests only", result,
          expect_projects=["backend"], exact=True)
finally:
    restore(fs_java, orig)

o1 = patch(fs_ts)
o2 = patch(fs_java)
try:
    result = tia(root=FS)
    check("Mixed .java + .ts change → both ecosystems", result,
          expect_projects=["backend", "frontend"], exact=True)
finally:
    restore(fs_ts, o1)
    restore(fs_java, o2)

print("\n── No changes ────────────────────────────────────────────────────────")

result = tia()
check("Clean working tree → no tests to run", result, no_tests=True)

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"  {PASS} passed  |  {FAIL} failed  |  {PASS+FAIL} total")
print(f"{'─'*60}")

if _stashed:
    _stash_pop()

sys.exit(0 if FAIL == 0 else 1)
