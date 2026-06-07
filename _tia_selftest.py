#!/usr/bin/env python3
"""Self-test: TIA scenarios against multi-app."""

import json, subprocess, sys
from pathlib import Path

REPO   = Path(__file__).parent
APP    = REPO / "multi-app"
SCRIPT = REPO / "assess_impact.py"

PASS = FAIL = 0


def tia(extra_args=()):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--unstaged", "--root", str(APP), "--output", "json", *extra_args],
        capture_output=True, text=True, cwd=str(REPO),
    )
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"_raw": r.stdout + r.stderr}


def check(label, result, *, expect_projects=None, run_all=None, exact=False, no_tests=False):
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
check(".csproj change → run_all", result, run_all=True)
restore(csproj, orig)

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
result = tia()
check("Config .json (Application) → Application.Tests or run_all", result,
      expect_projects=["MultiApp.Application.Tests"], exact=False)
git_rm_cached(cfg)
cfg.unlink()

# unknown extension → safe run_all fallback
unk = APP / "src/MultiApp.Domain/readme.xyz"
unk.write_text("unknown", encoding="utf-8")
git_add(unk)
result = tia()
check("Unknown file type (.xyz) → run_all", result, run_all=True)
git_rm_cached(unk)
unk.unlink()

print("\n── No changes ────────────────────────────────────────────────────────")

result = tia()
check("Clean working tree → no tests to run", result, no_tests=True)

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"  {PASS} passed  |  {FAIL} failed  |  {PASS+FAIL} total")
print(f"{'─'*60}")
sys.exit(0 if FAIL == 0 else 1)
