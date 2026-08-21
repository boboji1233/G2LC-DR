# ADR-0005: Packaging allowlist and external archive checksums

Status: accepted for Stage 1.6.1

Date: 2026-08-21

## Context

Stage 1.6 produced a 96,343-byte wheel and a 156,588,124-byte sdist. Hatch had no sdist
policy, while `.gitignore` excluded `.venv/` but not `.venv311` or `.venv312`. Those local
dual-Python environments were therefore eligible source-distribution inputs. The review
ZIP also embedded a gate referring to the previous ZIP digest because a file cannot contain
its own final cryptographic hash.

## Decision

1. Hatch uses a root-anchored sdist allowlist plus defense-in-depth exclusions for local
   environments, caches, generated outputs, medical-data roots, logs, checkpoints, build
   directories, and review bundles.
2. Every gate build writes to a unique ignored audit directory. The gate audits exactly one
   wheel and one sdist, enforces 2 MiB/5 MiB limits, scans members and contents, and clean-
   installs both archives before invoking the installed CLI.
3. Synthetic fixtures required by the CLI smoke test are force-included under
   `g2lc/fixtures/synthetic` in the wheel.
4. The embedded gate and metadata use `EXTERNALIZED` for the archive checksum. The final
   sibling `.sha256` and `_final_metadata.json` are jointly authoritative and are written
   only after the ZIP bytes are final.
5. Review exports normalize local absolute roots. Raw logs remain unchanged outside the
   archive, and the archive manifest hashes the normalized copies.

## Consequences

Repeated builds cannot recursively ingest prior build products. Review consumers must keep
the ZIP, `.sha256`, and final metadata together. This ADR changes no Stage 1.6 clinical,
logical, solver, repair, certificate, or independent-verifier semantics.
