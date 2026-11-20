# GLM-5.3 test-split results (Aliyun)

Completed on 2026-11-13 at approximately 15:52 Asia/Singapore. This is an additional-model
experiment using Aliyun's OpenAI-compatible Token Plan endpoint. It is separate from the
earlier, incomplete Ark GLM/Kimi runs; those records are not included or pooled here.

## Coverage and validation

- 2,700 unique episodes: 30 test scenarios × five configurations ×
  (four templates × two goals × two repeats + two clean repeats).
- 540 episodes/configuration: 60 clean, 240 G1 and 240 G2.
- G2 includes 180 instruction-bearing cases and 60 `direct` transcription-control cases
  per configuration; report these separately.
- Every canonical episode has `record.status=ok`; zero API errors and zero format failures.
  This means normal execution, not that every legitimate task or attack succeeded.
- Every returned model identifier in the recorded calls is `glm-5.3`.
- Gateway off, `body` insertion, original prompts, payloads, schemas and scoring.

## Recorded settings and provenance

Experiment code commit: `26ceac62925311b6217603c3feac03d94d35e106`, with clean
`harness/`, `data/` and `configs/` in the isolated runner checkout. The endpoint override
was supplied through an external profile, copied here as `model-profile.toml`.
The profile's name is `deepseek`, but `--model glm-5.3` selects the actual model; it does
not mean these are DeepSeek responses. Credential variable names are retained; no key
values are included.

The original `run_args.json` retains actual local paths and the final worker count.
Concurrency increased from 2 to 4 workers after 517 saved episodes, and from 4 to 8
after 939. `execution-history.jsonl` and `execution-checkpoints/` preserve the pre-change
settings, canonical prefixes and audits. Completed keys were retained; unrecorded in-flight
episodes could be attempted again after a restart. Such interrupted work can consume credits
without appearing as an additional canonical episode.

Do not interpret total elapsed time or pooled latency as a fixed-concurrency benchmark.
This additional-model/provider run was conducted after the original DeepSeek study; do not
represent it as a new prospectively selected model or pool it with historical Ark records.

## Files

- `episodes.jsonl.gz`: complete compressed raw episode records, including prompts, tool
  traces, handoffs, responses, per-call usage and scores.
- `summary.md`, `by_config.csv`: generated analysis, including instruction/control G2 rates.
- `run_args.json`, `model-profile.toml`: actual run metadata and portable endpoint profile.
- `execution-history.jsonl`, `execution-checkpoints/`: concurrency-phase audit records.
- `manifest.json`: checksums, file sizes and basic completeness checks. It excludes itself
  and this explanatory README.

The generated analysis retains the study's existing limitations: automatic handoff labels
and warning detection need human review; utility is based on key-fact matching; the current
summary does not supply every interaction or instruction-only paired contrast.

## Reproduce the analysis without API calls

From the repository root with the existing Python dependencies installed:

```bash
python -m harness.analyze results/test-glm-5.3-aliyun
```

The analyzer reads the gzip directly. Use the recorded code commit for exact reproduction
if the repository's analysis code changes later.

To launch a **new paid run**, use a separate output directory and a valid credential in
the variable specified in the profile:

```bash
python -m harness.run --profile deepseek \
  --config results/test-glm-5.3-aliyun/model-profile.toml --model glm-5.3 \
  --split test --gateway off --repeats 2 --clean-repeats 2 --workers 8 \
  --out results/test-glm-5.3-aliyun-reproduction
```

Re-running the model does not guarantee identical responses. No experiment code or existing
DeepSeek results are changed by this results-only contribution.
