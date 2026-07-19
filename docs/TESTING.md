# Testing

The test suite is split by **property, not by filename** — a pytest marker on
the test *is* its class. There is no hand-maintained list of "which tests CI
runs" to drift out of date; adding a new dep-light test gates automatically.

## The two sets

| Set | Selection | What it is | Where it runs |
| --- | --- | --- | --- |
| **fast** | `-m 'not requires_eda and not slow and not requires_services'` | pure-Python, no EDA binary / docker daemon / live service | every PR (CI `backend` job) |
| **heavy** | `-m 'requires_eda or slow or requires_services'` | needs a real toolchain / service / long run | nightly + local, opt-in |

```bash
# Fast set — what the PR gate runs (seconds, no toolchain needed):
pytest -m 'not requires_eda and not slow and not requires_services' -q

# Heavy set — run where the toolchain/services exist (locally or nightly):
pytest -m 'requires_eda or slow or requires_services' -q
```

## Markers (registered in `pytest.ini`)

- **`requires_eda`** — needs a real EDA binary or image: `iverilog`, `verilator`,
  `yosys`, `sby` (SymbiYosys), cocotb, XLS, ORFS / real synthesis.
- **`requires_services`** — needs a live external service or daemon: a real Docker
  daemon, Postgres, GCS / Cloud Run, WorkOS.
- **`slow`** — heavy / long-running end-to-end runs (real ORFS, real Cloud Run).

A test can carry more than one marker (e.g. the real-ORFS run is both
`requires_eda` and `slow`). Heavy tests keep their existing `skipif` / env-var
guards (`RUN_REAL_ORFS=1`, `RUN_REAL_CLOUD_RUN=1`, `shutil.which(...)`), so a bare
`pytest` run **skips** them cleanly rather than failing — the marker is what
*deselects* them from the fast gate.

### Marking a new heavy test

Module-level (the whole file is heavy):

```python
import pytest
pytestmark = pytest.mark.requires_eda
```

Per-test (only some tests in an otherwise dep-light file are heavy):

```python
@pytest.mark.requires_eda
def test_lint_and_simulate_end_to_end(client):
    ...
```

If you write a new **pure-Python** test, do nothing — it joins the fast set and
gates on every PR automatically.

## CI wiring

The fast set is the PR gate. In `.github/workflows/ci.yml`, the `backend` job's
unit-test step selects by marker (no filename list):

```yaml
    - name: Fast unit tests (pure-Python; selected by marker, not a filename list)
      env:
        PYTHONPATH: .
      run: |
        pytest -m 'not requires_eda and not slow and not requires_services' -q
```

The stdcell-bootstrap and post-synth-smoke steps stay exactly as they are — they
are the real-toolchain smoke coverage that runs alongside the fast unit set.

The heavy set's home is a separate, opt-in nightly job (`ci-nightly.yml`) that
installs the toolchain and runs `pytest -m 'requires_eda or slow or
requires_services'`; the cost/creds-gated tests additionally need
`RUN_REAL_ORFS=1` / `RUN_REAL_CLOUD_RUN=1`. Until that job exists, the heavy set
is **local-only** (run it with the command above where your toolchain lives) —
deferred, not dropped.
