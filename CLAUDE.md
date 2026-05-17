# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working style

### Before any code change

State assumptions explicitly. If multiple interpretations exist, name them and confirm before picking one. If a simpler approach exists, say so.

For multi-step tasks, state a brief plan first:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Transform vague requests into verifiable goals before starting — e.g. "fix the bug" → "reproduce it in a test, then make the test pass".

### Code changes

- Touch only what the request requires. Do not improve adjacent code.
- Match existing style. No abstractions or configurability beyond what was asked.
- Every changed line must trace directly to the request.
- If unrelated dead code is noticed, mention it — don't delete it.
- Remove only imports/variables/functions that **your** changes made unused.

### Response style

- No preamble, affirmations, or filler. Answer directly; lead with code when code is the answer.
- Omit explanation unless asked. If asked, max 3 sentences.
- Error responses: state what failed + fix only.

### File enumeration

Use `git ls-files --cached --others --exclude-standard` to enumerate source files.
To verify a specific path: `git check-ignore -v <path>`

**Skip directories** (any path segment matching these):

| Ecosystem | Skip directories |
|---|---|
| All | `.git/` `.github/` (actions are readable; secrets are not) |
| Java / Android | `build/` `.gradle/` `.cxx/` `.externalNativeBuild/` `captures/` |
| C# / .NET | `bin/` `obj/` `.vs/` `packages/` `.nuget/` |
| Node.js | `node_modules/` `dist/` `.next/` `.nuxt/` `.cache/` `coverage/` `.turbo/` |

**Skip file extensions** (compiled output, binaries, secrets):

| Ecosystem | Skip extensions |
|---|---|
| Java / Android | `.class` `.dex` `.apk` `.aab` `.aar` `.hprof` `.jks` `.keystore` |
| C# / .NET | `.dll` `.exe` `.pdb` `.nupkg` `.snupkg` |
| Node.js | `.map` (source maps) |
| All | `.log` `.lock` (e.g. `package-lock.json`, `yarn.lock`, `packages.lock.json`) |

**Skip specific filenames:**

`local.properties`, `lint-results*`, `*.user`, `*.suo`, `*.DS_Store`

On a blocked path: state the path, ask for the source file instead.

### Tool permission labels

Prefix every permission prompt with one of:

- `[READ-ONLY]` — reads only, no state change
- `[MUTATION]` — modifies files/state, recoverable via git
- `[DESTRUCTIVE]` — irreversible (delete, force-push, drop table)
- `[SYSTEM]` — touches packages, permissions, OS-level config

### Test failure triage

Default assumption: **the application is wrong, not the test.** The test is a specification of correct behaviour.

Decision tree — follow in order, stop at first match:

1. Test asserts something the app genuinely should do → fix the application, do not touch the test.
2. A recent change intentionally altered the behaviour the test was specifying → update the test, document why in a comment.
3. Test asserts the wrong thing (wrong expected value, tests internal implementation, assumption never true) → fix the test; state _"this test was wrong because …"_ before changing it.
4. Test environment is the problem (flaky clock, shared state, missing double, OS-specific path) → fix the infrastructure; do not weaken the assertion.

Never: delete a failing test, change an assertion to match broken output, mark a test ignored without a filed issue + expiry condition, or weaken an assertion to paper over a regression.

## What this repo is

A **Test Impact Analysis (TIA)** tool for C# / .NET projects. Given a git diff, `assess_impact.py` selects only the tests whose execution path could have been affected by the change — avoiding a full suite run on every push.

The `sample-app/` directory is a self-contained C# solution used to verify the script against realistic dependency scenarios.

## Running the script

```bash
# Analyse the last commit (most common usage)
python assess_impact.py --base HEAD~1 --root sample-app

# Analyse unstaged/staged working-tree changes (no commit needed)
python assess_impact.py --unstaged --root sample-app

# Analyse AND immediately run dotnet test
python assess_impact.py --base HEAD~1 --root sample-app --run

# Machine-readable output for CI scripting
python assess_impact.py --base HEAD~1 --root sample-app --output json

# CI integration outputs
python assess_impact.py --base HEAD~1 --root sample-app --output github-actions
python assess_impact.py --base HEAD~1 --root sample-app --output azure-devops

# Pass extra flags to dotnet test
python assess_impact.py --base HEAD~1 --root sample-app --run -- --no-build --verbosity minimal
```

`--root` is the directory searched for `.sln` / `.csproj` files. It does not need to be the git repo root — the script detects the actual git root via `git rev-parse --show-toplevel` independently.

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
FileChange list  ─── classify_change() ──→  INFRA | IGNORED | CS_SOURCE | CONFIG | UNKNOWN
    ↓
discover_projects()          parse .sln → .csproj (merged with glob; excludes obj/bin)
    ↓
build_reverse_deps()         BFS-transitive graph: {source_path → set[test_paths]}
    ↓
build_test_file_cache()      pre-load all test .cs files into memory once
    ↓
per-file analysis loop
  ├─ strategy_dependency_graph()   project ownership → reverse dependency lookup
  ├─ strategy_convention()         FooService → FooServiceTests (both old+new paths for renames)
  └─ strategy_symbol_search()      extract public types → grep cached test files
    ↓
build_filter()               "FullyQualifiedName~A|FullyQualifiedName~B" (capped at 40 classes)
    ↓
ImpactResult → formatter → stdout
```

### File classification rules (in priority order)

| Category | Trigger | Behaviour |
|---|---|---|
| `INFRA` | `.sln`, `.csproj`, `global.json`, `nuget.config`, `Directory.Build.*` | Run all test projects |
| `IGNORED` | `.md`, images, archives; dotfiles: `.gitignore`, `.editorconfig` | Skip — no tests |
| `CS_SOURCE` | `.cs` | Full 3-strategy analysis |
| `CONFIG` | `.json`, `.xml`, `.yaml`, `.resx`, `.razor`, `.cshtml`, etc. | Find owning project, run its tests |
| `UNKNOWN` | Anything else | Run all tests (safe fallback) |

### Safe fallback chain

When targeted selection fails, the script escalates rather than silently skipping tests:
1. Unmatched `.cs` file → run all test projects
2. Source project changed but nothing in the dependency graph covers it → run all test projects
3. Config file with no owning project → run all test projects

### Key data structures

- `FileChange(path, old_path, status)` — renames carry both paths; `analysis_paths()` returns both for renames so convention + dependency graph fire against the old name too.
- `CSharpProject(name, path, is_test_project, project_references)` — `project_references` holds stem names (what appears in `<ProjectReference Include="...">`).
- `ImpactResult` — the unified output consumed by all formatters and the test runner.
- `reverse_deps: Dict[Path, Set[Path]]` — maps each source project path to the set of test project paths that should run when it changes (BFS-resolved).

### Test project detection (in order)

1. Explicit `<IsTestProject>true</IsTestProject>` in the csproj
2. Any known test NuGet package (`xunit`, `nunit`, `mstest.testadapter`, `moq`, `fluentassertions`, etc.)
3. Project name ends with `.Tests`, `.Test`, `.Specs`, `.Spec` (case-insensitive)

## Sample-app dependency graph

```
SampleApp.Core          (no deps)
    ↑
SampleApp.Services      (→ Core)
    ↑
SampleApp.Api           (→ Services)   [no test project]

SampleApp.Core.Tests    tests Core      (92 tests)
SampleApp.Services.Tests tests Services (60 tests)
```

**Implication:** changing anything in `Core` triggers **both** test projects (transitive BFS). Changing `Services` only triggers `Services.Tests`.

## Extending to other languages

The script is structured so each language needs only its own `discover_projects()` equivalent and three strategy functions. The git analysis, file classification, output formatting, and CI integration layers are language-agnostic.

The `ChangeCategory` enum and the fallback escalation chain in `assess()` are the two places that would need to handle new file extensions.
