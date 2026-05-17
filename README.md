# Test Impact Analysis — C# / .NET

Analyses a git diff and selects only the tests whose execution path could have been affected by the change. Skips the full suite on every push.

**No external dependencies** — Python 3.8+ stdlib only.

---

## Requirements

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.8+ | Run the script |
| Git | any | Diff source |
| .NET SDK | 8.0+ | Build and run `sample-app` tests |

---

## Quick start

```bash
# Analyse the last commit against the one before it
python assess_impact.py --base HEAD~1 --root <path-to-your-solution>

# Analyse uncommitted (staged + unstaged) changes — no commit needed
python assess_impact.py --unstaged --root <path-to-your-solution>

# Analyse and immediately run the selected tests
python assess_impact.py --base HEAD~1 --root <path-to-your-solution> --run
```

`--root` is where the `.sln` / `.csproj` files live. It does not need to be the git root — the script locates the actual git root automatically via `git rev-parse --show-toplevel`.

---

## Testing the script with sample-app

`sample-app/` is a self-contained C# solution with **152 unit tests** across two test projects, designed to exercise every code path in the script.

```
SampleApp.Core       (no deps)            ← 92 tests in SampleApp.Core.Tests
    ↑
SampleApp.Services   (depends on Core)    ← 60 tests in SampleApp.Services.Tests
    ↑
SampleApp.Api        (depends on Services) [no test project]
```

### Step 1 — Confirm tests pass clean

```bash
cd sample-app
dotnet test SampleApp.sln
# Expected: 152 passed, 0 failed
```

### Step 2 — Run a scenario

Make a change, then run the script. Use either workflow:

**A. Commit-based** (matches real CI behaviour):

```bash
# From the repo root
echo "// change" >> sample-app/src/SampleApp.Core/Models/Product.cs
git add .
git commit -m "test: touch Product.cs"

python assess_impact.py --base HEAD~1 --root sample-app
```

**B. Unstaged** (faster, no commit needed):

```bash
echo "// change" >> sample-app/src/SampleApp.Core/Models/Product.cs

python assess_impact.py --unstaged --root sample-app

# Undo
git checkout sample-app/src/SampleApp.Core/Models/Product.cs
```

### Step 3 — Verify the output

```
──────────────────────────────────────────────────────────────────
  TEST IMPACT ANALYSIS
──────────────────────────────────────────────────────────────────
  Status  : RUN ALL TESTS          ← "Targeted run" = good; "RUN ALL" = fallback triggered
  Affected test projects (2):
    • SampleApp.Core.Tests
    • SampleApp.Services.Tests
  Affected test classes (4):
    • InventoryServiceTests
    • OrderServiceTests
    • ProductServiceTests
    • ProductTests
  dotnet command:
    dotnet test "...SampleApp.sln"
```

### Scenario reference

Each scenario tests a distinct behaviour of the script:

| Scenario | File to change | Expected result |
|---|---|---|
| **A** Core model | `sample-app/src/SampleApp.Core/Models/Product.cs` | Both test projects (transitive BFS) |
| **B** Service only | `sample-app/src/SampleApp.Services/PricingService.cs` | `Services.Tests` + filter `PricingServiceTests` |
| **C** Test file | `sample-app/tests/SampleApp.Core.Tests/Utilities/StringHelperTests.cs` | `Core.Tests` + filter `StringHelperTests` |
| **D** Config file | `sample-app/src/SampleApp.Services/appsettings.json` | `Services.Tests`, no class filter |
| **E** Infrastructure | `sample-app/src/SampleApp.Services/SampleApp.Services.csproj` | `run_all = true`, both projects |
| **F** Ignored file | `sample-app/.gitignore` | No tests (skipped entirely) |

Run a scenario:

```bash
# Scenario A — Core change triggers both test projects
echo "// change" >> sample-app/src/SampleApp.Core/Models/Product.cs
git add . && git commit -m "scenario A"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit

# Scenario B — Service change triggers only Services.Tests
echo "// change" >> sample-app/src/SampleApp.Services/PricingService.cs
git add . && git commit -m "scenario B"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit

# Scenario C — Editing a test file targets only that class
echo "// change" >> sample-app/tests/SampleApp.Core.Tests/Utilities/StringHelperTests.cs
git add . && git commit -m "scenario C"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit

# Scenario D — Config file runs project-level (no class filter)
echo "{}" >> sample-app/src/SampleApp.Services/appsettings.json
git add . && git commit -m "scenario D"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit

# Scenario E — Infrastructure file forces run-all
echo "<!--change-->" >> sample-app/src/SampleApp.Services/SampleApp.Services.csproj
git add . && git commit -m "scenario E"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit

# Scenario F — Ignored file skips tests entirely
echo "# change" >> sample-app/.gitignore
git add . && git commit -m "scenario F"
python assess_impact.py --base HEAD~1 --root sample-app
git revert HEAD --no-edit
```

---

## Usage reference

```
python assess_impact.py [OPTIONS] [-- DOTNET_ARGS]

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
python assess_impact.py --base HEAD~1 --root sample-app

# JSON — pipe into scripts or CI steps
python assess_impact.py --base HEAD~1 --root sample-app --output json

# GitHub Actions — prints `echo "key=value" >> $GITHUB_OUTPUT` lines
python assess_impact.py --base HEAD~1 --root sample-app --output github-actions

# Azure DevOps — prints `##vso[task.setvariable ...]` lines
python assess_impact.py --base HEAD~1 --root sample-app --output azure-devops
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
  run: python assess_impact.py --base ${{ github.event.before }} --root sample-app --output github-actions

- name: Run affected tests
  if: steps.tia.outputs.has_tests == 'true'
  run: ${{ steps.tia.outputs.dotnet_command }}
```

Available outputs: `test_filter`, `run_all`, `has_tests`, `test_project_paths`, `dotnet_command`.

### Azure DevOps

```yaml
- script: python assess_impact.py --base $(System.PullRequest.TargetBranch) --root sample-app --output azure-devops
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
