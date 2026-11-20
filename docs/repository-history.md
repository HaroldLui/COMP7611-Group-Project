# Repository history

Before submission (2026-11-20) the repository history was condensed into a single commit, tagged
`v1.0-submission`. Commit IDs quoted in earlier documents and run records (for example the frozen
code commit `3df873e` in `docs/preregistration.md` and `docs/dev-pilot-report.md`, and the
`code_commit` values in `results/*/run_args.json`) refer to the pre-condensation history and no
longer resolve on GitHub. They are kept unchanged as part of the record.

## Frozen code versus this snapshot

`data/` is identical to the frozen code. `harness/` and `configs/` differ from it only by the
removal of one unused optional model backend that no reported run used:

- `harness/config.py`, `harness/llm.py`: backend class and its factory branch removed
- `harness/env.py`, `harness/llm_openai.py`: docstring wording only
- `harness/run.py`: that backend's SDK version no longer recorded in `run_args.json`
- `configs/models.toml`: the corresponding profile removed

Every reported run used the `openai`-compatible backend, whose code path is unchanged.
