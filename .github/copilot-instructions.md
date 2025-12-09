# AI Coding Agent Guide for gocql-driver-matrix

This repository orchestrates matrix testing of the Go `gocql` driver (both Scylla fork and upstream) against Scylla/Cassandra clusters, generating JUnit XML and optional email reports. Use these instructions to work productively within this codebase.

## Architecture Overview
- **Entry point:** `main.py` parses arguments, resolves driver versions/tags, protocols, and test sets, then iterates a matrix and delegates to `Run`.
- **Runner:** `run.py::Run` encapsulates one matrix cell:
  - Checks out the requested driver tag in `gocql_driver_git`.
  - Applies version-specific patches from `versions/<driver_type>/<tag>/patch*`.
  - Spawns a local Scylla cluster via `ccmlib` using `cluster.py::TestCluster`.
  - Executes Go tests with tailored flags and pipes output through `go-junit-report`, producing part files.
  - Merges parts and post-processes results in `processjunit.py` using ignore/flaky rules from `versions/**/ignore.yaml` per protocol.
  - Writes metadata and a final xunit file under `xunit/<driver_version>/`.
- **Configuration:** `configurations.py` maps logical test sets (`integration`, `ccm`) to `go test` args and cluster settings.
- **Reporting:** `email_sender.py` renders `report_templates/report.html` and can send email via SMTP using credentials pulled from S3.

## Key Data/Control Flows
- **Driver selection:** `main.py:get_driver_type()` inspects `remote.origin.url` to infer `scylla` vs `upstream`.
- **Version resolution:** `--versions` can be a count (N latest tags discovered via `git tag --sort=-creatordate`) or explicit tags (e.g., `v1.8.0,v1.7.3`).
- **Protocol handling:** `--protocols` accepts comma-separated native protocol versions (e.g., `3,4`) and maps to `-proto=<n>`; ignore rules use `tests` for proto 3 and `v<n>_tests` (e.g., `v4_tests`) for proto 4.
- **Ignore rules:** `versions/<driver_type>/<tag>/ignore.yaml` may include `ignore`, `flaky`, `skip`. Post-processing will:
  - Reclassify test outcomes to `ignored_in_analysis`, `flaky`, `xpassed`, `xfailed` when appropriate.
  - Summarize counts and rewrite the final JUnit file for Jenkins consumption.
- **Patch application:** For each `patch*` file in the version directory, `Run._apply_patch_files()` runs `git apply --stat`, `git apply --check` (with a special case for `tests/integration/conftest.py`), then `patch -p1 -i`.

## Developer Workflows
- **Local run (Python):**
  - Create venv and install deps:
    ```bash
    virtualenv -p python3.10 venv
    source venv/bin/activate
    pip install -r scripts/requirements.txt
    pip install ../scylla-ccm
    ```
  - Run matrix against upstream/scylla repos:
    ```bash
    python3 main.py ../gocql-upstream --tests integration --versions 1 --protocols 3,4 --scylla-version release:5.2.4
    python3 main.py ../gocql-scylla   --tests integration --versions v1.8.0 --protocols 3,4 --scylla-version release:5.2.4
    ```
  - **Required args:** `--scylla-version` must be provided unless `SCYLLA_VERSION` is set in the environment (enforced in `main.py`). Ensure `GOCQL_DRIVER_DIR` points to the driver repo root containing `go.mod`.
- **Dockerized run:**
  ```bash
  export GOCQL_DRIVER_DIR="$(pwd)/../gocql-scylla"
  scripts/run_test.sh --tests integration --versions 1 --protocols 3 --scylla-version release:5.2.4
  ```
- **Outputs:** JUnit is written to `xunit/<driver_tag>/xunit.<driver_type>.v<proto>.<tag>.xml` plus `*_part_*` files during test execution. Metadata JSON is written alongside.
- **Email report:** Use `--recipients` to trigger an email with rendered HTML. Requires AWS credentials to read `scylla-qa-keystore` and SMTP access.
 
## CI and Scripts
- **Jenkins entrypoint:** `scripts/run_test.sh` is the job’s command wrapper. Example:
  ```bash
  GOCQL_DRIVER_DIR=/path/to/gocql-scylla \
  /path/to/gocql-driver-matrix/scripts/run_test.sh \
    --tests integration ccm --versions 2 --protocols 3,4 \
    --recipients someone@example.com
  ```
- **Docker image:** Tag stored in `scripts/image`; `run_test.sh` runs `docker run` with mounts:
  - `/gocql-driver-matrix` ← repo root (`$GOCQL_MATRIX_DIR`)
  - `/gocql` ← driver repo (`$GOCQL_DRIVER_DIR`)
  - `/scylla-ccm` ← CCM repo (`$CCM_DIR`)
  - Mounts Jenkins `WORKSPACE` if present, forwards `BUILD_*`, `JOB_*`, `AWS_*`, `SCYLLA_*` envs.
- **Container run details:** Runs detached and streams logs via `docker logs -f`. Container uses the invoking user’s UID/GID and adds all host groups to avoid permission issues on mounted volumes.
- **Container entrypoint:** `scripts/entrypoint.sh` validates mounts, installs `/scylla-ccm`, then runs:
  ```bash
  cd /gocql-driver-matrix && python3 main.py /gocql "$@"
  ```
- **Dockerfile highlights:**
  - Base: Python 3.10 + Go 1.25; installs `go-junit-report@v2.0.0` into `/usr/local/go-packages/bin`.
  - Installs OS deps (`libssl-dev`, `git`, `openjdk-11-jdk-headless`, `gcc`, `build-essential`).
  - Copies `entrypoint.sh`; sets `ENTRYPOINT`.
- **Python deps:** `scripts/requirements.txt` includes `boto3`, `Jinja2`, `PyYAML`, `pytest`, etc. The container installs via multi-stage.

## Conventions and Patterns
- **Version-specific overrides:** Place `ignore.yaml` and optional `patch*` under `versions/<driver_type>/<tag>/`. Use `master` directory for non-semver identifiers.
- **Patch mechanics:** Patches exist to make historical driver tags build and test cleanly against modern Scylla/Cassandra and toolchains. `Run._apply_patch_files()` iterates any `patch*` files in `versions/<driver_type>/<tag>/` and applies them in order:
  - Shows stats via `git apply --stat`, validates via `git apply --check`.
  - Special-case: if `--check` fails due to `tests/integration/conftest.py`, it removes that file to allow patching.
  - Applies with `patch -p1 -i <file>`, so patch hunks are relative to repo root.
  - Typical fixes include minor test adjustments, build flags, or compatibility tweaks specific to that tag.
  - If a patch fails, the run is aborted and `metadata_*.json` is written with failure details.
  - Naming: use `patch`, `patch1`, `patch2`, …; files are applied in lexical order.
- **Go test invocation:** Built from `configurations.py` with additional flags:
  - `-proto`, `-autowait`, `-compressor=snappy`, `-gocql.cversion` derived from `SCYLLA_VERSION` or default `3.11.4`.
  - For Scylla driver `>= v1.16.1`, appends `-distribution=scylla`.
  - Cluster params from `TestCluster.start()`: `-rf`, `-clusterSize`, `-cluster`, and optional `-cluster-socket`.

## Adding New Versions
- **Where to add:** Create a folder `versions/<driver_type>/<tag>/` where `<driver_type>` is `scylla` or `upstream` and `<tag>` matches the driver tag (e.g., `1.16.1`).
- **Minimum files:**
  - `ignore.yaml` with protocol-specific keys: `tests` (proto 3) and `v4_tests` (proto 4). Include `ignore`, `flaky`, `skip` lists as needed.
  - Optional `patch` or `patch*` files for compatibility tweaks.
- **When to include a patch:**
  - Build breaks under modern toolchains (Go version, CGO, OpenSSL).
  - Tests reference outdated cluster APIs or assume legacy behavior incompatible with current Scylla/Cassandra.
  - Flags or tags changed (e.g., distribution-specific behaviors for Scylla starting `>= v1.16.1`).
  - Minor test stabilization needed (race conditions, timing via `-autowait`, legacy test helpers).
- **Patch authoring tips:**
  - Generate diffs from the driver repo root so hunks apply with `patch -p1`.
  - Keep patches surgical and tag-specific; avoid broad refactors.
  - Validate locally with `main.py` or `scripts/run_test.sh` against the exact tag.
  - If `git apply --check` complains about `tests/integration/conftest.py`, remove it; the runner handles this special case.
- **Version resolution behavior:**
  - `--versions N` takes the latest `N` semver tags discovered via `git tag --sort=-creatordate` (deduping major.minor).
  - Non-semver identifiers resolve to `versions/<driver_type>/<id>/` or fall back to `versions/<driver_type>/master`.
- **JUnit merging:** Part files are merged by `processjunit._merge_part_results()` keyed by the module from `go.mod` (default `github.com/gocql/gocql`). Failures/errors in earlier parts are preserved.
- **Protocol-aware ignore keys:** Protocol 3 uses `tests`; protocol 4 looks for `v4_tests` in `ignore.yaml`.
- **Environment propagation:** `Run.environment` injects `PROTOCOL_VERSION` and `SCYLLA_VERSION` into subprocesses. `subprocess` uses `/bin/bash`.
- **CI env passthrough:** `run_test.sh` forwards `BUILD_*`, `JOB_*`, `AWS_*`, `SCYLLA_*`, and `WORKSPACE` to docker; use these in reporting.

## External Integrations
- **ccmlib:** Manages Scylla clusters in `cluster.py`. Ensure `scylla-ccm` is installed and cluster directories live under `<driver_repo>/ccm`.
- **AWS S3 via boto3:** `email_sender.KeyStore` reads `email_config.json` from bucket `scylla-qa-keystore`.
- **go-junit-report:** CLI required in PATH to convert `go test -v` output into JUnit XML.
 - **Docker:** Container requires bind mounts to the three repos (`/gocql-driver-matrix`, `/gocql`, `/scylla-ccm`); entrypoint enforces presence.

## Practical Tips for Agents
- When adding support for a new driver tag, create `versions/<driver_type>/<tag>/ignore.yaml` and any necessary `patch` files. Verify `Run.version_folder` resolves correctly.
- Prefer surgical changes: update `configurations.py` for new test tags or flags; adjust `Run.run()` only if command structure changes.
- Use `ProcessJUnit.save_after_analysis()` to keep Jenkins-compatible counts and classnames: it prefixes classnames with `"<type>_version_<tag>_v<proto>_"`.
- If email sending is enabled in CI, ensure AWS and SMTP credentials exist; otherwise, omit `--recipients` during local runs.
- For failures in patch application, inspect special handling for `tests/integration/conftest.py` and the `patch -p1` semantics.

## Examples and References
- Driver module detection: `Run._get_driver_module()` is a private method that reads `go.mod` from the driver repo (using `self._gocql_driver_git`) and falls back to `github.com/gocql/gocql` if not found.
- Ignore structure example: see `versions/scylla/1.16.1/ignore.yaml` and `versions/upstream/*/ignore.yaml`.
- Report template: `report_templates/report.html` rendered via Jinja2.

---
If any part of these instructions is unclear or missing (e.g., additional test tags, CI hooks, or ignore YAML schema variants), tell me what you’d like documented and I’ll refine this guide.