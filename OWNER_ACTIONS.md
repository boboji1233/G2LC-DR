# Owner Actions

1. Review the Stage-1.6 commit diff, `artifacts/audit/stage1_6/gate.json`, and the archive
   whose filename contains the full commit SHA.
2. Push the Stage-1.6 branch only after local review; no automation in this task pushes,
   merges, or reopens a pull request.
3. Require green GitHub Actions for Python 3.11 and 3.12 plus human review before merge.
4. Keep Stage 2, real-data parsing, Oracle experiments, and visual training frozen until
   a separately authorized, provenance-safe next task begins.
5. Treat the weekly/manual 2,000-case semantic stress job as additional evidence, not a
   substitute for the mandatory 200-case PR gate.
