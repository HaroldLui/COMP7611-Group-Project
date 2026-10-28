# Multi-Agent Handoffs and Prompt Injection

Group project: *Does Multi-Agent Decomposition Increase or Reduce Prompt-Injection Risk? The
Role of Handoff Format and User-Intent Preservation.*

The project has three parts:
- **A harness** that runs a single agent (A) and four reader → planner → executor pipelines
  (M1–M4) on synthetic meeting-document tasks, with injected attacks.
- **Rule-based scoring** of attack success, task utility and cost.
- **Analysis** using a paired bootstrap that resamples scenarios.

Pipelines M1–M4 vary two things: free text vs. JSON handoffs, and whether the executor sees
the user's request.

## Demo (macOS/Linux, about 15 seconds, no API key)

```bash
cd ~/Desktop/mas-injection-study
./demo.sh                 # offline: tests, all 5 configurations, results table, two traces
./demo.sh deepseek        # same, then checks a real profile (needs .env)
```

To view any episode as a readable trace (handy for slides):
`python -m harness.show results/demo --config M1 --goal G1`

## Quick start (offline, no API key)

```bash
python data/make_scenarios.py                     # 5 dev + 30 test scenarios -> data/scenarios.json
python -m unittest discover -s tests -v           # offline tests
python -m harness.run --profile fake --split dev --out results/fake-dev
python -m harness.analyze results/fake-dev
```

The **fake** profile is a deterministic, deliberately gullible rule-based stand-in. It exists to
test the plumbing. **Its numbers are not results**, and `summary.md` says so.

## Setting up your model

1. **Install dependencies:** `pip install -r requirements.txt`. You only need the SDK of the
   backend you use.
2. **Add your key:** `cp .env.example .env`, then fill in the key for your provider. `.env`
   is git-ignored. Never put keys in `configs/models.toml`.
3. **Pick a profile:** open `configs/models.toml`, choose one (or copy one), and set `model`.
   Ready-made profiles: `openai`, `deepseek`, `qwen`, `gemini`, `openrouter`, `local` (Ollama/vLLM),
   `claude`. Any OpenAI-compatible endpoint works through `backend = "openai"` plus `base_url`.
4. **Check it works** (2–3 tiny calls):

   ```bash
   python -m harness.check --profile deepseek
   ```

   It confirms that the model calls the `send_email` tool correctly. **A model that fails this
   check can't be used**: the whole study depends on tool calling.

## Running on a real model

```bash
python -m harness.run --profile deepseek --split dev --dry-run                # plan size only
python -m harness.run --profile deepseek --split dev --configs A,M1,M2 \
    --repeats 1 --clean-repeats 1 --out results/pilot-dev --workers 4
python -m harness.analyze results/pilot-dev --annotate 30
```

- **Resumable:** re-running the same command skips episodes already in `episodes.jsonl`.
- **Budget control:** use `--max-episodes N` to cap a run, and `--dry-run` to see the plan
  size first.
- **Recorded settings:** each run saves the profile it used (without keys) in
  `results/<name>/run_args.json`.
- **Settings to fix before the test run:**
  - `temperature`: leave it unset (provider default) or fix one value.
  - `max_tokens_param`: newer OpenAI models need `max_completion_tokens`.
  - `reasoning_effort`: for reasoning models.
  - `extra_body`: provider-specific switches, e.g. turning a model's thinking mode on or off.

  Record whatever you choose in `docs/preregistration.md`.
- **Adding a provider that isn't OpenAI-compatible:** write a class with
  `complete(system, messages, tools) -> Turn` (see `harness/llm_openai.py` for the pattern)
  and register it in `harness/config.py`.

**Rough cost:** an M-configuration episode makes about 8 model calls. Check `tokens_per_ep`
in the pilot's `summary.md` and multiply by the planned episode count (2,700 for the main run)
and your provider's price before starting the test split.

## Sharing results (GitHub)

Commit each real run's folder, but compress the raw log first: `episodes.jsonl` itself is
git-ignored because big runs can exceed GitHub's file-size limits.

```bash
gzip -k results/pilot-dev/episodes.jsonl          # creates episodes.jsonl.gz, keeps the original
git add results/pilot-dev
git commit -m "Add dev pilot results (<model>)"
git push
```

`harness.analyze` and `harness.show` read `episodes.jsonl.gz` directly, so teammates can analyze
a pulled run without unzipping it.

## Layout

```
data/make_scenarios.py    template-based scenario generator (fictional people, .example domains)
configs/models.toml       model profiles (provider, model, settings); keys go in .env
harness/config.py         profile + .env loading, backend factory
harness/llm.py            backend interface, Anthropic backend, offline fake backend
harness/llm_openai.py     OpenAI-compatible backend (OpenAI, DeepSeek, Qwen, Gemini, OpenRouter, Ollama, vLLM)
harness/check.py          one-command connection + tool-calling check for a profile
harness/show.py           print one episode as a readable trace
demo.sh                   one-command offline demo
harness/env.py            scenario model, mock tools (list_docs, read_doc, send_email), gateway
harness/attacks.py       4 payload templates × 2 goals, planting, company-domain markers
harness/handoff.py        strict JSON schemas (ReaderNotes, EmailPlan), parsing + repair rule
harness/prompts.py        role prompts (freeze after the dev pilot)
harness/agents.py         tool-use loop, full call logging
harness/pipeline.py       configurations A, M1–M4 and the episode runner
harness/scoring.py        ASR-G1/G2, attempt rate, utility, handoff labels, cost
harness/run.py            batch runner -> results/<name>/episodes.jsonl
harness/analyze.py        summary.md, by_config.csv, annotation.csv
docs/preregistration.md   hypotheses, rules and analysis plan; freeze before test runs
paper/                    LaTeX skeleton + refs.bib
```

## Safety

Every tool is mocked: `send_email` only writes to the log. Attacker addresses and URLs
masquerade under the fictional company's own domain (`records-<hash>@<company>.example`,
`https://training.<company>.example/register/<hash>`); `.example` is a reserved TLD that can never
resolve, and the per-episode hash keeps scoring exact. People and companies are fictional.

## Team workflow

1. **Dev split:** tune prompts, check that configuration A shows non-zero attack success,
   and measure cost.
2. **Freeze:** fill in and commit `docs/preregistration.md`.
3. **Test split:** run the full plan, then run `analyze --annotate 80`. Two people label the
   annotation sheet.
4. **Write-up:** fill in the paper's §7–§9 from `summary.md`.
