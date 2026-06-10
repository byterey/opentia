# opentia — Test Impact Analysis

Analyses a git diff and selects only the tests whose execution path could have been affected by the change. Skips the full suite on every push.

**No external dependencies** — Python 3.8+ stdlib only.

**Language support:** C# / .NET, Java (Maven / Gradle), Android (Kotlin, nested Gradle modules, instrumented tests), and Node.js (Jest / Vitest / npm test scripts — single packages, npm/pnpm/lerna workspaces). Mixed-language repos are handled in a single run: changes are routed to the right ecosystem automatically.

---

## Requirements

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.8+ | Run opentia |
| Git | any | Diff source |

---

## Installation

```bash
pip install opentia
```

This installs the `opentia` command on your `PATH`.

---

## Quick start

```bash
# Analyse the last commit
opentia --base HEAD~1 --root <path-to-your-project>

# Analyse uncommitted (staged + unstaged) changes — no commit needed
opentia --unstaged --root <path-to-your-project>

# Analyse and immediately run the selected tests
opentia --base HEAD~1 --root <path-to-your-project> --run
```

`--root` is where your `.sln` / `.csproj` / `pom.xml` / `build.gradle` / `package.json` lives. It does not need to be the git root — opentia locates the actual git root automatically.

---

## Usage reference

```
opentia [OPTIONS] [-- TEST_ARGS]

  --base REF      Git ref to diff against (e.g. HEAD~1, main, origin/main)
  --head REF      Head ref to diff from (default: HEAD)
  --root DIR      Directory containing project files (default: .)
  --lang LANG     Force one adapter: dotnet | java | node (default: auto-detect all)
  --strategy      project | convention | symbol | hybrid (default: hybrid)
  --output, -o    human | json | github-actions | azure-devops (default: human)
  --run           Execute the test command after analysis
  --unstaged      Analyse working-tree changes (staged + unstaged)
  --staged        Analyse only staged changes — useful before committing
  --              Everything after this is forwarded to the test runner
```

### Output formats

```bash
# Human-readable (default)
opentia --base HEAD~1 --root .

# JSON — pipe into scripts or CI steps
opentia --base HEAD~1 --root . --output json

# GitHub Actions
opentia --base HEAD~1 --root . --output github-actions

# Azure DevOps
opentia --base HEAD~1 --root . --output azure-devops
```

### JSON output fields

```jsonc
{
  "run_all": false,               // true = targeted selection was abandoned
  "language": "dotnet",          // dotnet | java | node
  "test_filter": "FullyQualifiedName~PricingServiceTests",
  "test_project_paths": ["...SampleApp.Services.Tests.csproj"],
  "affected_test_projects": ["SampleApp.Services.Tests"],
  "affected_test_classes": ["PricingServiceTests"],
  "test_command": "dotnet test \"...\" --filter \"...\"",
  "reason": "Analysis complete",
  "strategy_notes": []            // warnings / fallback explanations
}
```

When changes span multiple ecosystems in one run, the same fields are emitted merged at the top level (`language: "java,node"`, `test_command` joined with `&&`) plus a `results` array containing one full per-language object each.

---

## Node.js projects

opentia detects Jest and Vitest automatically. For **workspaces** (npm `workspaces`, `pnpm-workspace.yaml`, or `lerna.json`), each sub-package is analysed independently and the dependency graph is resolved across internal references — `workspace:*`, `file:`, **and plain version ranges** that match a sibling package name. Changing a shared package triggers tests in every package that depends on it.

The test command is a single `npx jest` (or `npx vitest run`) invocation run from the workspace root with a test-path-pattern filter. Packages without jest/vitest but with a `test` script (karma, `ng test`, mocha-via-script) fall back to `npm test --prefix <package>` — selection stays package-accurate, but those packages run their full suite.

## Android projects

Android repos are handled by the Gradle adapter with Kotlin-aware analysis (Kotlin types and functions are public by default — no modifier needed for symbol matching). Per module:

- Unit tests (`src/test`) run via `./gradlew :path:to:module:test --tests=...`; instrumented tests (`src/androidTest`) are selected separately and routed to `:path:to:module:connectedAndroidTest` (device/emulator required).
- Nested module references (`project(":core:model")`) resolve by path, and each module's command carries only its own test classes — a `--tests` pattern matching nothing would fail the task.
- `gradle/libs.versions.toml` is workspace-level INFRA (full run); `local.properties`, keystores (`.jks`/`.keystore`), `build/` output, and hidden tooling dirs (`.github/`, `.claude/`, …) are ignored; `proguard-rules.pro` scopes to its owning module.
- Method-level narrowing only applies when every changed method in a test class is `@Test`-annotated; a changed helper widens to the whole class.

## Mixed-language monorepos

A single run covers every ecosystem under `--root`. Each changed file is routed to the adapter owning its nearest build file (`.csproj`/`.sln`, `pom.xml`/`build.gradle`, `package.json`), so a fullstack repo — say a Maven backend with an Angular frontend — selects backend tests for `.java` changes and frontend specs for `.ts` changes in one invocation:

```bash
opentia --base HEAD~1 --root .   # all ecosystems, one combined result
```

The combined `test_command` chains each runner with `&&`. To restrict analysis to one ecosystem, pass `--lang dotnet|java|node`.

Two more monorepo behaviours worth knowing:

- **Changes outside `--root` are ignored** (reported in `strategy_notes`) rather than triggering a full run of the app you pointed at.
- **Module-level build files** (a leaf `.csproj`, a module `pom.xml`, a workspace package's `package.json`) scope through the dependency graph like any other change to that project. Only workspace-level files (`.sln`, root/parent `pom.xml`, `settings.gradle`, root `package.json`, lockfile-style global config) force a full run.

---

## CI integration

### GitHub Actions — pull request

```yaml
on:
  pull_request:
    branches: [main, staging]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Test Impact Analysis
        id: tia
        run: opentia --base ${{ github.event.pull_request.base.sha }} --root . --output github-actions

      - name: Run affected tests
        if: steps.tia.outputs.has_tests == 'true'
        run: ${{ steps.tia.outputs.test_command }}
```

Available outputs: `test_filter`, `run_all`, `has_tests`, `test_project_paths`, `test_command`.

### GitHub Actions — push to branch

```yaml
- name: Test Impact Analysis
  id: tia
  run: opentia --base ${{ github.event.before }} --root . --output github-actions

- name: Run affected tests
  if: steps.tia.outputs.has_tests == 'true'
  run: ${{ steps.tia.outputs.test_command }}
```

### Azure DevOps

```yaml
- script: opentia --base $(System.PullRequest.TargetBranchName) --root . --output azure-devops
  displayName: Test Impact Analysis

- script: $(testCommand)
  condition: eq(variables['hasTests'], 'true')
  displayName: Run affected tests
```

Available variables: `testFilter`, `runAllTests`, `hasTests`, `testProjectPaths`, `testCommand`.
