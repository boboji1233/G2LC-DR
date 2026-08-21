# Scripts

Future acquisition helpers must be explicit user-invoked tools, verify licenses and
checksums, and never download gated datasets automatically.

Stage 1.6 uses three checked scripts:

- `stage1_6_baseline_probe.py` runs against the detached `ec3250d...` source tree and
  intentionally exits 1 when every expected pre-fix defect is reproduced.
- `stage1_6_capture_baseline.py` verifies the immutable baseline and records the source
  manifest plus the probe output under `artifacts/audit/stage1_6/`.
- `stage1_6_gate.py` records the locked environment, static checks, tests/coverage,
  build, 200-case semantic differential suite, audit, short-SHA review bundle, and final
  bundle verification. It does not push, open a PR, or merge.

