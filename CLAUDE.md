# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **multi-language Test Impact Analysis (TIA)** tool, published to PyPI as `opentia`. Given a git diff, `assess_impact.py` selects only the tests whose execution path could have been affected by the change — avoiding a full suite run on every push.

Supported ecosystems via `LanguageAdapter` subclasses: **C# / .NET** (`.sln`/`.csproj`), **Java / Android** (Maven + Gradle; Kotlin-aware, nested Gradle modules, `src/androidTest` → `connectedAndroidTest`), **Node.js** (Jest / Vitest / npm test scripts; npm, pnpm, and lerna workspaces). Polyglot repos are handled in one run — changes are partitioned to the adapter owning their nearest build-file ancestor.

The repo contains tracked validation apps (see _Validation apps_ below) and a scenario harness, `_tia_selftest.py`.

## Running the script

```bash
# Analyse the last commit (most common usage)
python assess_impact.py --base HEAD~1 --root sample-app

# Analyse unstaged/staged working-tree changes (no commit needed)
python assess_impact.py --unstaged --root sample-app

# Analyse AND immediately run the selected tests
python assess_impact.py --base HEAD~1 --root sample-app --run

# Machine-readable output for CI scripting
python assess_impact.py --base HEAD~1 --root sample-app --output json

# CI integration outputs
python assess_impact.py --base HEAD~1 --root sample-app --output github-actions
python assess_impact.py --base HEAD~1 --root sample-app --output azure-devops

# Force one adapter in a polyglot repo (default: auto-detect all)
python assess_impact.py --base HEAD~1 --root java-fullstack-app --lang java

# Pass extra flags to the test runner
python assess_impact.py --base HEAD~1 --root sample-app --run -- --no-build --verbosity minimal
```

`--root` is the directory searched for build files. It does not need to be the git repo root — the script detects the actual git root via `git rev-parse --show-toplevel` independently. **Changes outside `--root` are ignored** (with a strategy note), they do not trigger fallback runs.

## Running the scenario harness

```bash
python _tia_selftest.py   # all TIA scenarios against the validation apps
```

**Important:** the harness stashes the working tree (including untracked files) before running and pops afterwards — so it always exercises the **committed** `assess_impact.py`, not uncommitted edits. When developing: verify changes with direct `--unstaged` invocations first, commit, then run the harness.

## Running the sample-app tests

```bash
cd sample-app

# All tests
dotnet test SampleApp.sln

# Single test project
dotnet test tests/SampleApp.Core.Tests/SampleApp.Core.Tests.csproj
dotnet test tests/SampleApp.Services.Tests/SampleApp.Services.Tests.csproj

# Single test class (dotnet filter syntax)
dotnet test tests/SampleApp.Core.Tests/SampleApp.Core.Tests.csproj --filter "FullyQualifiedName~ProductTests"

# Multiple test classes (pipe = OR)
dotnet test SampleApp.sln --filter "FullyQualifiedName~ProductTests|FullyQualifiedName~OrderTests"
```

## Architecture of assess_impact.py

The script has no external dependencies — stdlib only. The pipeline on every invocation:

```
git diff (--name-status)
    ↓
detect_adapters()            every ecosystem under --root (priority: dotnet > java > node)
    ↓
partition_changes()          polyglot only: route each file to the adapter owning its
                             nearest build-file ancestor; unowned files → all adapters
    ↓  per adapter — assess():
root scoping                 drop changes outside --root (with a note)
adapter.classify()           INFRA | IGNORED | SOURCE | CONFIG | UNKNOWN
adapter.discover()           parse build files (pruned walk via _iter_files —
                             node_modules/obj/bin/target skipped during descent)
build_reverse_deps()         BFS-transitive graph: {source_path → set[test_paths]};
                             refs resolved by path (.NET), group:artifact (Maven),
                             package name (Node — incl. plain-version internal deps)
adapter.build_test_file_cache()
per-file analysis loop
  ├─ strategy_dependency_graph()   project ownership → reverse dependency lookup
  ├─ strategy_convention()         FooService → FooServiceTests (both old+new paths for renames)
  ├─ strategy_symbol_search()      extract public types → grep cached test files
  └─ method-level refinement       changed source methods → matching test methods by name
adapter.build_filter()       runner-specific filter (capped at 40 identifiers)
    ↓
ImpactResult per adapter → formatter → stdout
                             (CI formats merge multi-language results; json adds
                              a `results` array when >1 language)
```

### File classification rules (in priority order)

| Category  | Trigger (per adapter)                                                                 | Behaviour                                                                                                                |
| --------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `INFRA`   | build files: `.sln`/`.csproj`, `pom.xml`/`build.gradle`, `package.json`, tool configs | **Tiered:** workspace-level → run all; module-level build file → scope via dependency graph and drop class-level filters |
| `IGNORED` | `.md`, images, archives; dotfiles: `.gitignore`, `.editorconfig`                      | Skip — no tests                                                                                                          |
| `SOURCE`  | `.cs` / `.java` `.kt` / `.ts` `.js` etc.                                              | Full 3-strategy analysis                                                                                                 |
| `CONFIG`  | `.json`, `.xml`, `.yaml`, `.resx`, `.razor`, `.properties`, etc.                      | Find owning project, run its tests + dependents                                                                          |
| `UNKNOWN` | Anything else                                                                         | Run all tests (safe fallback)                                                                                            |

Workspace-level = `.sln`, root/parent `pom.xml`, `settings.gradle`, root `package.json`, `pnpm-workspace.yaml`, `libs.versions.toml`, `global.json`, `Directory.Build.*`. Module-level = a discovered project's own build file. Files under hidden tooling dirs (`.github/`, `.claude/`, `.vscode/`, …) and `local.properties` are always IGNORED.

### Safe fallback chain

When targeted selection fails, the script escalates rather than silently skipping tests:

1. Unmatched source file → run all test projects
2. Source project changed but nothing in the dependency graph covers it → run all test projects
3. Config file with no owning project → run all test projects

### Key data structures

- `FileChange(path, old_path, status)` — renames carry both paths; `analysis_paths()` returns both for renames so convention + dependency graph fire against the old name too.
- `Project(name, path, is_test_project, project_references, reference_paths, group_id)` — `reference_paths` holds resolved build-file paths (exact, collision-proof; .NET); `project_references` holds names (`group:artifact` qualified for Maven, package names for Node); `group_id` is the Maven groupId.
- `LanguageAdapter` (ABC) — per-ecosystem: `detect`, `has_build_file` (polyglot routing), `classify`, `discover`, the two name-based strategies, `build_filter`, `run_tests`, `fmt_command`.
- `ImpactResult` — the unified output consumed by all formatters and the test runner; `_merge_results()` collapses multi-language results for the flat CI formats.
- `reverse_deps: Dict[Path, Set[Path]]` — maps each source project path to the set of test project paths that should run when it changes (BFS-resolved).

### Test project detection

- **.NET:** `<IsTestProject>true</IsTestProject>` → known test NuGet package (`xunit`, `nunit`, `moq`, …) → name ends `.Tests`/`.Test`/`.Specs`/`.Spec`.
- **Java / Android:** `src/test/java|kotlin` or `src/androidTest/java|kotlin` exists, or a test-scoped / known test dependency (`junit`, `mockito`, `robolectric`, `mockk`, `espresso-core`, …). Mixed modules (source + tests in one module) are normal; `is_test_file()` (`src/test/` or `src/androidTest/` in path) distinguishes within the module. Gradle class filters are scoped per module; instrumented classes route to `connectedAndroidTest`.
- **Node:** jest/vitest/jasmine in deps or a `test` script; in workspaces, sub-packages owning `.test.`/`.spec.`/`__tests__` files. The workspace root itself is the runner, never a test project.

## Validation apps

| App                   | Shape                                                                    | Exercises                                                                                           |
| --------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `sample-app/`         | C# 3-layer + 2 test projects                                             | transitive BFS (Core → both test projects)                                                          |
| `multi-app/`          | C# 4-layer diamond                                                       | layer isolation; `_tia_selftest.py` default target                                                  |
| `java-sample-app/`    | single Maven module                                                      | single-module behaviour                                                                             |
| `java-multi-app/`     | Maven 4-module diamond                                                   | Java mixed modules, transitive deps                                                                 |
| `java-fullstack-app/` | Maven backend + Angular frontend                                         | polyglot routing, karma `npm test` fallback                                                         |
| `node-sample-app/`    | single npm package                                                       | single-package Node                                                                                 |
| `node-mono-app/`      | npm workspaces (`workspace:*` deps)                                      | workspace dependency graph                                                                          |
| `node-plain-mono/`    | pnpm-style (plain-version internal deps, hoisted jest)                   | pnpm/lerna detection, name-matched dep edges                                                        |
| `collision-app/`      | two C# apps, same-stem `Core.csproj`                                     | path-based ProjectReference resolution                                                              |
| `java-collision-app/` | two Maven apps, colliding `core` artifactIds                             | group:artifact qualified matching                                                                   |
| `android-app/`        | Kotlin, nested Gradle modules (`:core:model`), unit + instrumented tests | Kotlin symbols/methods, androidTest routing, nested refs, per-module filters, version-catalog INFRA |
| `gradle-nested/`      | settings.gradle one level below `--root`                                 | ref resolution anchored at the settings root, not `--root`                                          |

## Extending to other languages

Subclass `LanguageAdapter`, implement its abstract methods (plus `has_build_file` for polyglot routing), and append an instance to `_ADAPTERS`. The git analysis, change partitioning, fallback escalation, output formatting, and CI integration layers are language-agnostic.

Add a validation app for the new ecosystem and scenarios to `_tia_selftest.py` — every adapter behaviour in this repo is specified by a harness scenario first.
