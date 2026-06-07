# opentia — Test Impact Analysis

Analyses a git diff and selects only the tests whose execution path could have been affected by the change. Skips the full suite on every push.

**No external dependencies** — Python 3.8+ stdlib only.

**Language support:** C# / .NET is fully supported. Java (Maven/Gradle) and Node.js support are planned for future releases.

---

## Requirements

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.8+ | Run the script |
| Git | any | Diff source |
| .NET SDK | 8.0+ | Build and run `sample-app` tests |

---

## Installation

```bash
pip install opentia
```

This installs the `opentia` command on your `PATH`.

## Publishing to PyPI

```bash
python -m build && twine upload dist/* --username __token__ --password pypi-YOUR_TOKEN
```

---

## Quick start

```bash
# Analyse the last commit against the one before it
opentia --base HEAD~1 --root <path-to-your-solution>

# Analyse uncommitted (staged + unstaged) changes — no commit needed
opentia --unstaged --root <path-to-your-solution>

# Analyse and immediately run the selected tests
opentia --base HEAD~1 --root <path-to-your-solution> --run
```

`--root` is where the `.sln` / `.csproj` files live. It does not need to be the git root — the script locates the actual git root automatically via `git rev-parse --show-toplevel`.

---

## Validating the script with sample-app

`sample-app/` is a self-contained C# solution purpose-built to verify the script against realistic dependency scenarios.

### Dependency graph

```
SampleApp.Core       (no deps)             ← 92 tests in SampleApp.Core.Tests
        ↑
SampleApp.Services   (depends on Core)     ← 60 tests in SampleApp.Services.Tests
        ↑
SampleApp.Api        (depends on Services)   [no test project]
```

**Key implication:** changing anything in `Core` triggers **both** test projects because `Services` depends on `Core` — the BFS propagates transitively.

### Step 1 — Confirm baseline

```bash
cd sample-app
dotnet test SampleApp.sln
# Expected: 152 passed, 0 failed
cd ..
```

### Step 2 — Run validation scenarios

Each scenario tests a distinct behaviour. Use `--unstaged` to avoid committing:

**Scenario 1 — Ignored file → no tests selected**

```bash
echo "# change" >> sample-app/.gitignore
opentia --unstaged --root sample-app
# Expected: no tests to run (file type is ignored)
git checkout sample-app/.gitignore
```

**Scenario 2 — Services-only change → only `Services.Tests`**

```bash
echo "// change" >> sample-app/src/SampleApp.Services/PricingService.cs
opentia --unstaged --root sample-app
# Expected: SampleApp.Services.Tests only, filtered to PricingServiceTests
git checkout sample-app/src/SampleApp.Services/PricingService.cs
```

**Scenario 3 — Core change → both test projects (transitive)**

```bash
echo "// change" >> sample-app/src/SampleApp.Core/Utilities/MathHelper.cs
opentia --unstaged --root sample-app
# Expected: SampleApp.Core.Tests AND SampleApp.Services.Tests
# Services.Tests is included because Services depends on Core (BFS)
git checkout sample-app/src/SampleApp.Core/Utilities/MathHelper.cs
```

**Scenario 4 — Infrastructure change → all tests forced**

```bash
echo " " >> sample-app/SampleApp.sln
opentia --unstaged --root sample-app
# Expected: run_all = true, all test projects
git checkout sample-app/SampleApp.sln
```

### Step 3 — Read the output

```
──────────────────────────────────────────────────────────────────
  TEST IMPACT ANALYSIS
──────────────────────────────────────────────────────────────────
  Status  : Targeted run            ← "RUN ALL TESTS" means a fallback was triggered
  Affected test projects (1):
    • SampleApp.Services.Tests
  Affected test classes (1):
    • PricingServiceTests
  dotnet command:
    dotnet test "...SampleApp.Services.Tests.csproj" --filter "FullyQualifiedName~PricingServiceTests"
──────────────────────────────────────────────────────────────────
```

`Status: Targeted run` means the script selected a subset. `Status: RUN ALL TESTS` means it fell back to running everything (expected for Scenario 4).

### Additional scenarios

| File to change | Expected result |
|---|---|
| `src/SampleApp.Core/Models/Product.cs` | Both test projects, filtered to `ProductTests` + dependent service tests |
| `tests/SampleApp.Core.Tests/Utilities/StringHelperTests.cs` | `Core.Tests` only, filtered to `StringHelperTests` |
| `src/SampleApp.Services/appsettings.json` | `Services.Tests`, no class filter (config file) |
| `src/SampleApp.Services/SampleApp.Services.csproj` | All tests, `run_all = true` (infra file) |

---

## Usage reference

```
opentia [OPTIONS] [-- DOTNET_ARGS]

  --base REF      Git ref to diff against (e.g. HEAD~1, main, origin/main)
  --head REF      Head ref to diff from (default: HEAD)
  --root DIR      Directory containing .sln / .csproj files (default: .)
  --strategy      project | convention | symbol | hybrid (default: hybrid)
  --output, -o    human | json | github-actions | azure-devops (default: human)
  --run           Execute dotnet test after analysis
  --unstaged      Analyse working-tree changes instead of a git diff
  --              Everything after this is forwarded to dotnet test
```

### Strategies

| Strategy | What it does |
|---|---|
| `project` | Parse `.sln`/`.csproj` to find which test projects reference the changed source project (BFS-transitive through the dependency graph) |
| `convention` | `FooService.cs` → look for `FooServiceTests.cs`, `FooServiceTest.cs`, `TestFooService.cs` |
| `symbol` | Extract `public class/interface/enum` names from the changed file; grep all test `.cs` files for references |
| `hybrid` | All three combined (default) |

### Output formats

```bash
# Human-readable (default)
opentia --base HEAD~1 --root sample-app

# JSON — pipe into scripts or CI steps
opentia --base HEAD~1 --root sample-app --output json

# GitHub Actions — prints `echo "key=value" >> $GITHUB_OUTPUT` lines
opentia --base HEAD~1 --root sample-app --output github-actions

# Azure DevOps — prints `##vso[task.setvariable ...]` lines
opentia --base HEAD~1 --root sample-app --output azure-devops
```

### JSON output fields

```jsonc
{
  "run_all": false,               // true = targeted selection was abandoned
  "test_filter": "FullyQualifiedName~PricingServiceTests",
  "test_project_paths": ["...SampleApp.Services.Tests.csproj"],
  "affected_test_projects": ["SampleApp.Services.Tests"],
  "affected_test_classes": ["PricingServiceTests"],
  "dotnet_command": "dotnet test \"...\" --filter \"...\"",
  "reason": "Analysis complete",
  "strategy_notes": []            // warnings / fallback explanations
}
```

---

## CI integration

### GitHub Actions

```yaml
- name: Test Impact Analysis
  id: tia
  run: opentia --base ${{ github.event.before }} --root sample-app --output github-actions

- name: Run affected tests
  if: steps.tia.outputs.has_tests == 'true'
  run: ${{ steps.tia.outputs.dotnet_command }}
```

Available outputs: `test_filter`, `run_all`, `has_tests`, `test_project_paths`, `dotnet_command`.

### Azure DevOps

```yaml
- script: opentia --base $(System.PullRequest.TargetBranch) --root sample-app --output azure-devops
  displayName: Test Impact Analysis

- script: $(dotnetCommand)
  condition: eq(variables['hasTests'], 'true')
  displayName: Run affected tests
```

Available variables: `testFilter`, `runAllTests`, `hasTests`, `testProjectPaths`, `dotnetCommand`.

---

## How it works

```
git diff --name-status base..head
    ↓
classify each file → INFRA | IGNORED | CS_SOURCE | CONFIG | UNKNOWN
    ↓
INFRA  → run all tests
IGNORED→ skip
UNKNOWN→ run all tests (safe fallback)
CS_SOURCE / CONFIG → run 3 strategies ↓

discover_projects()      parse .sln + glob .csproj (excludes obj/ bin/)
build_reverse_deps()     BFS: {source_project → set of test projects that cover it}
    ↓ per CS_SOURCE file:
  strategy 1: project dependency graph (ownership → reverse dep lookup)
  strategy 2: convention mapping (FooService → FooServiceTests)
  strategy 3: symbol search (public types → grep cached test files)
    ↓ per CONFIG file:
  find owning project → run its test projects (no class filter)
    ↓
build_filter()           FullyQualifiedName~A|FullyQualifiedName~B
                         capped at 40 classes; drops to project-level if exceeded
    ↓
ImpactResult → formatter → stdout
```

**Fallback escalation** — rather than silently skipping tests, the script escalates:
1. `.cs` file not owned by any known project → run all test projects
2. Source project changed but dependency graph finds no covering tests → run all test projects
3. Config file not owned by any project → run all test projects

---

## Extending to other languages

To add Python, Node.js, or Java support, provide:

1. A `discover_projects()` equivalent that returns `List[Project]` for that ecosystem
2. Three strategy functions matching the signatures of `strategy_dependency_graph`, `strategy_convention`, `strategy_symbol_search`
3. New entries in `INFRA_EXTENSIONS`, `IGNORED_EXTENSIONS`, and `CONFIG_EXTENSIONS` for that ecosystem's file types

The git analysis, file classification pipeline, output formatters, and CI integration are language-agnostic and require no changes.
