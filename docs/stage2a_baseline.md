# Stage 2A starting baseline

Recorded on 2026-08-21 (Asia/Shanghai), before Stage 2A tracked changes.

## Git and dependency identity

- Starting branch: `codex/stage2-data-governance`
- Starting commit: `f362c2666fe4b615f8ab528fe6b630fa2a24dfa3`
- Starting tree: `dfb66e4852f9de5181c2bd192facb43f482efe01`
- Merged Stage-1.6.1 head: `2c63b68bd67b9366f86e62533b56efecb156ea26`
- Ancestor check: `git merge-base --is-ancestor 2c63b68... f362c26...` exited `0`.
- Starting tracked worktree: clean.
- Starting `uv.lock` SHA-256:
  `93ff60d1c8107c622e2ea3438b52e2828bb6d8be488a655473cbd921fb454463`.

The starting commit is the merge commit for PR #2; both cited commits resolve to the
same starting tree.

## Stage 1.6.1 prerequisite result

The exact portable command was run before Stage 2A changes:

```bash
uv run --python 3.11 python scripts/stage1_6_gate.py
```

`G2LC_REQUIRED_PYTHONS=3.11,3.12` and the pinned `uv` 0.12.5 executable were supplied.
The commit-bound aggregate gate reported `PASS`: 484 recorded test executions, zero
failures, Python 3.11.16 and 3.12.14, whole-project line/branch coverage
93.9046%/87.4499%, and core line/branch coverage 96.6241%/91.1088%.

## Starting CI assumptions

- Ubuntu GitHub-hosted runners; checkout fetch depth is zero.
- `astral-sh/setup-uv@v6`, pinned to `uv` 0.12.5.
- Required Python matrix: 3.11 and 3.12.
- Locked dependency sync, ruff, formatting, strict mypy, branch-aware pytest, isolated
  build/package audit, installed CLI smoke tests, and commit-bound review verification.
- Weekly/manual semantic stress remains separate from the per-push quality matrix.

No GitHub Actions run result is inferred from local evidence. The Stage 2A gate records
local and CI subprocess exit codes independently.

## Scope at authorization

Stage 2A permits metadata governance and Oracle-input readiness only. No medical image
was downloaded, no target label was fabricated, no guideline/Oracle execution occurred,
and no visual model, training loop, checkpoint, or experiment result was introduced.
