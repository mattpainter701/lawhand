# Backend test shards

The backend suite is the long pole in CI. It runs as four shard jobs
(`test-backend-shard`), each of which packs a disjoint set of test files and
then runs them with `pytest -n 4 --dist loadfile` (pytest-xdist).

## How files are assigned

`backend/scripts/shard_tests.py` assigns whole files to shards — never tests
within a file, so module-level fixtures and intra-file ordering are preserved.
It uses greedy longest-processing-time packing, and two weighting modes:

- **Measured durations** (`--durations tests/ci_durations.json`): each file is
  weighted by the summed per-test wall time from a real CI run. A file with no
  recorded timings (new or renamed) falls back to the median measured per-test
  cost, so every weight stays in seconds.
- **Heuristic** (default, and the fallback when the file is absent): test count
  times a per-test cost reflecting whether the file uses the `db_session`/`client`
  fixtures and the per-test `TRUNCATE` they trigger.

`--fixed-load SHARD:SECONDS` adds pinned per-shard work that is not part of the
packed files — shard 1 runs the LibreOffice install and the durable-workflow
suite, shard 2 owns the Studio fact-review database — so those shards receive
proportionally fewer files.

## Refreshing the measured durations

The shard jobs upload their pytest JUnit XML as `backend-junit-shard-<n>`
artifacts. Dispatch **Refresh backend test durations** (`.github/workflows/ci-durations.yml`)
after a CI run finishes; it downloads those artifacts, writes
`backend/tests/ci_durations.json` with
`backend/scripts/junit_to_durations.py`, and opens or updates a PR. It does not
run the suite again.

Refresh it when the shard balance drifts — that is, when one shard is
consistently slower than the others in the CI job list.

## Running the sharder locally

```bash
cd backend
python scripts/shard_tests.py --shards 4 --index 1                 # heuristic
python scripts/shard_tests.py --shards 4 --index 1 \
  --durations tests/ci_durations.json --fixed-load 1:71 --fixed-load 2:18
python scripts/shard_tests.py --shards 4 --index 1 --summary       # balance
```
