# routing-bench

A small harness for comparing **model-routing setups in Claude Code** on the number that matters: **cost per successful task**, not price per token.

Each task is a short Python problem with a prompt, starter code, and tests. The runner gives Claude Code a fresh scratch directory, lets it edit, then grades with **hidden pytest tests** the agent did not have. A run passes only when those tests pass. The headline for a setup is:

**cost per passing task** = sum of computed cost across every attempt ÷ number of distinct tasks that passed at least once

Failed attempts stay in the numerator. A cheap setup that often fails can cost more per success than a dearer setup that passes.

This is a learning tool. It does not ship results. The file `samples/FAKE_example_results.jsonl` is invented data so you can try the analyzer before spending anything.

## Quick start

From this repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or: uv venv && uv pip install -r requirements.txt

cp .env.example .env
# put a credential in .env if you will do more than a dry run

python -m bench --dry-run --pilot
python analyze.py samples/FAKE_example_results.jsonl --csv /tmp/fake-summary.csv
```

`--dry-run` prints the `claude` commands and writes nothing. It does not call a model.

`--pilot` is the first real spend: **task t1, every setup, one repetition**. Read the JSONL before you launch the full grid.

```bash
set -a && source .env && set +a
python -m bench --pilot
python analyze.py results/runs.jsonl --csv results/summary.csv
```

The full grid is every task, every setup, `--reps 1` (use `--reps 2` when you want a second noisy draw):

```bash
python -m bench --reps 1
```

Other flags: `--only A,F`, `--tasks t1,t6`, `--scratch-dir`, `--out`, `--claude`. Run `python -m bench --help`.

Scratch directories default to a fresh folder under the system temp directory, **outside this repo**, so the agent is not sitting next to the hidden tests. The path is printed. Pass `--scratch-dir` to keep it somewhere else. If that path is inside the repo, the runner warns you: a shell-capable agent can read the tests.

## What a run does

For each setup × task × repetition the runner:

1. Copies that task's `starter/` into an empty directory and adds `tests/visible/`. Hidden tests are not copied.
2. Runs `claude -p` once per step in the setup (setup C has a plan step and a build step).
3. Copies the canonical visible tests back (so an edited test file cannot weaken the grade) and copies `hidden_tests/` in.
4. Runs pytest. Pass means every visible and hidden test passed.
5. Appends one JSONL row per role/model it can see.

Default permission mode is `acceptEdits` plus `--allowedTools Read,Edit,Write,Glob,Grep,Bash` and `--permission-prompts none`, which is the documented way to run unattended without hanging on a prompt. Use it only because the workspace is disposable. `--permission-prompts` needs Claude Code v2.1.259 or later.

`--bare` is on by default so a machine's hooks, skills, plugins, and `CLAUDE.md` do not change the run. Bare mode does not use a subscription login. Set `ANTHROPIC_API_KEY`, or a gateway credential, in the environment.

Each invocation is killed after `timeout_seconds` (900 by default).

## Point it at a gateway

Nothing in this repo names a gateway or pins a URL. Configuration is environment variables Claude Code already documents:

| Variable | Role |
| --- | --- |
| `ANTHROPIC_BASE_URL` | Gateway base URL. Leave unset to use Claude Code's normal provider. |
| `ANTHROPIC_AUTH_TOKEN` | Bearer credential (`Authorization: Bearer`). |
| `ANTHROPIC_API_KEY` | Credential sent as `x-api-key`, or a direct API key when you are not using a gateway. |
| `ANTHROPIC_CUSTOM_HEADERS` | Extra `Name: Value` headers, one per line. |
| `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` | What the `opus` / `sonnet` / `haiku` aliases resolve to behind a gateway. Setting the Haiku pin also moves background tasks such as session titles onto that model. |

Model names in `setups.example.yaml` are `${MODEL_STRONG:-opus}`, `${MODEL_MID:-sonnet}`, `${MODEL_CHEAP:-haiku}`, and `${MODEL_ADVISOR:-opus}`. Those defaults are Claude Code family aliases. On the Anthropic API today they resolve to Opus 5.5, Sonnet 5.5, and Haiku 5.5. On other providers the same alias can be an older model. Override the variables, or set the `ANTHROPIC_DEFAULT_*_MODEL` pins, when you need a specific id.

Per-run tags go out through `ANTHROPIC_CUSTOM_HEADERS`, which is the documented extension point. Set `BENCHMARK_GATEWAY_HEADERS` (see `.env.example`) to a template with `{setup}`, `{task}`, `{role}`, `{run_id}`, and `{experiment}`. The example uses generic `X-Benchmark-*` headers. If your gateway only indexes a metadata header, put that header name in the template. Set the variable to `off` to send none.

Claude Code also sends its own attribution headers (`x-claude-code-session-id`, `x-claude-code-request-class`, `x-claude-code-agent-type`, and others). This harness does not invent those. `request-class` is how a gateway can tell a main-loop request from a subagent request without any benchmark header.

The runner loads `.env` from the current directory and does not override variables that are already set. `.env` is gitignored.

`via_gateway` in the JSONL is true when `ANTHROPIC_BASE_URL` is set. `cost_usd_gateway` is always null: this harness does not know how to read your gateway's bill. Fill that column from the gateway if you need it. If the gateway swaps the model, Claude Code's `cost_usd_client` is an estimate for the model it thinks it called, and it can be wrong. Compare the three cost columns; disagreement is a result.

## Setups

`setups.example.yaml` is the experiment. Copy it if you want to edit.

| Id | Idea | How it is invoked |
| --- | --- | --- |
| A | Mid-tier model does everything | `--model` mid alias |
| B | Cheap model does everything | `--model` cheap alias |
| C | Strong model plans, cheap model builds | Plan step: `--permission-mode plan`. Build step: cheap model, reading `PLAN.md` |
| D | Cheap model plus a stronger advisor | `--advisor`, plus a system line asking for a few consultations |
| E | Mid-tier model, cheap subagents | `CLAUDE_CODE_SUBAGENT_MODEL` (a subagent's own `model` field overrides it; `--bare` does not load custom subagents) |
| F | Strong model at low effort | `--model` strong alias, `--effort low` |

Setup C is two processes. Claude Code's `opusplan` alias plans with Opus and then builds with Sonnet, so it cannot express "Opus plans, Haiku builds."

Plan mode blocks source edits and writes the plan under `plansDirectory`. The runner sets that to `./plans` and, if `PLAN.md` was not written, copies the newest file from `./plans` to `PLAN.md` for the builder. A headless plan session does not click the interactive approve prompt; the builder is a separate `claude` process.

When a step's advisor is off, the child process gets `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` so a saved advisor in your user settings does not leak into the run. Subagent model `inherit` removes `CLAUDE_CODE_SUBAGENT_MODEL` from the child so your shell cannot leak one either. `CLAUDE_CODE_EFFORT_LEVEL` is set to the step's effort because that variable is applied before `--effort`.

Do not set `DISABLE_TELEMETRY` on advisor runs. Claude Code turns the advisor on through a feature flag, and that variable blocks the fetch, so the advisor stays off.

## Observability stack

```bash
cd observability
docker compose up -d
```

Grafana is at <http://localhost:3000> with anonymous admin **on localhost only**. Prometheus is at <http://localhost:9090>. The collector receives OTLP on `localhost:4317` (gRPC) and `localhost:4318` (HTTP).

For each real run, export the variables below. The runner does not turn telemetry on by itself. When `CLAUDE_CODE_ENABLE_TELEMETRY=1` is already set, it adds `experiment`, `setup`, `task`, `role`, and `run_id` to `OTEL_RESOURCE_ATTRIBUTES` so a gateway-side or Grafana view can be filtered. `run_id` as a metric label is acceptable on one machine and a bad idea beyond that.

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative
export OTEL_METRIC_EXPORT_INTERVAL=5000
export OTEL_LOGS_EXPORT_INTERVAL=5000
```

Those names and the `cumulative` temporality preference are from the Claude Code monitoring docs. Prompt text stays redacted unless you also set `OTEL_LOG_USER_PROMPTS=1`. Leave that off.

Claude Code exports `claude_code.cost.usage` (USD) and `claude_code.token.usage` with `type` of `input`, `output`, `cacheRead`, or `cacheCreation`. The `input` type **excludes** cache read and cache write. Attributes include `model`, `query_source` (`main`, `subagent`, or `auxiliary`), and `effort`. The `claude_code.api_request` event carries `cost_usd`, token counts, `duration_ms`, and `query_source`.

The collector writes events to `observability/data/claude-code-events.jsonl` and exposes Prometheus metrics on port 8889. **Check `http://localhost:8889/metrics` after the pilot.** The exporter renames metrics (dots become underscores, and unit or `_total` suffixes get added). The Grafana queries use the likely names and will be empty until they match what your collector actually emits. Short runs often end before Prometheus scrapes, so treat the JSONL from this harness, and the events file, as the per-run record.

Pass rate and cost per passing task are not Claude Code metrics. They need the hidden tests. After a batch:

```bash
python analyze.py results/runs.jsonl \
  --csv results/summary.csv \
  --prom observability/data/metrics.prom
```

The `benchmark-summary` container serves that file to Prometheus. The pass-rate panels stay empty until the file exists.

`docker` was not available where this repo was assembled, so the stack was checked by parsing the YAML and the dashboard JSON (`tests/test_observability.py`), not by booting it.

## How to read results

```bash
python analyze.py results/runs.jsonl --csv results/summary.csv
```

The table is one row per setup:

| Column | Meaning |
| --- | --- |
| runs | Distinct `run_id`s |
| pass_rate | Runs whose tests passed ÷ runs |
| mean_cost_usd | Sum of `cost_usd_computed` ÷ runs. A missing cost counts as 0 and is warned about. |
| cost_per_passing_task_usd | Sum of `cost_usd_computed` over **all** rows ÷ distinct tasks that passed at least once |
| mean_latency_ms | Mean per-run wall time. Wall time is stored once per Claude process, then summed across the plan and build steps. |
| cache_hit_ratio | `cache_read` ÷ (`input_uncached` + `cache_read` + `cache_write_5m` + `cache_write_1h`) |
| consult_rate | Runs with `advisor_calls` > 0 ÷ runs. Null means the result did not show a count, and those runs are not counted as consultations. |

`samples/FAKE_example_results.jsonl` is labeled fake in the filename and in every row's `notes`. The analyzer prints a banner when it sees that. Do not quote it as a measurement.

## JSONL

One JSON object per line, schema `routing-v1`. A run with several models (main model plus advisor, or main model plus subagents) produces several rows. Token and cost fields on a row are that model's share, so you can sum them. `wall_ms`, `turns`, and `tool_calls` are recorded on the step's main row only, so summing those across rows does not double-count.

`cost_usd_computed` uses `prices.yaml`, copied from the public pricing page on 2026-10-08 for Opus 5.5, Sonnet 5.5, and Haiku 5.5 (the up-to-100k-token tier). `cost_usd_client` is whatever Claude Code reported for that model (`modelUsage` when present, else `total_cost_usd`). Both are estimates. `cost_usd_gateway` is left null.

`usage` on the result covers the main loop only. `modelUsage` includes subagents, which is why the harness prefers it when it is present. Cache-write 5-minute vs 1-hour counts are taken from `usage.cache_creation` when there is a single model and the totals match. Otherwise the whole cache write is stored in `cache_write_5m` and the row says so.

## Caveats

- **Advisor token accounting is not documented** on the Claude Code cost or monitoring pages. The API's top-level `usage` counts the executor, and advisor tokens live elsewhere. This harness emits an `advisor` row only when `modelUsage` contains a model that matches the configured advisor and not the main model. If it cannot see that split, `advisor_calls` stays null unless the JSON payload actually contains advisor tool-use blocks. Treat consult rate as "observable calls," and check one advisor pilot against the provider console before you believe the dollar figure.
- **Non-Claude models through a gateway are not supported.** The Claude Code gateway docs say Anthropic does not support routing Claude Code to non-Claude models through any gateway. Expect tool, cache, and thinking breakage, and wrong client-side costs. This harness does not configure that path.
- **Gateway fallbacks are not a quality cascade.** This harness does not configure fallbacks. Products that document a fallback chain generally run it when the upstream returns an HTTP error, not when the model returns a wrong answer that still has status 200. Confirm that in your gateway's own docs. The response model is what you want in `model_served`; a fallback can change it without Claude Code noticing.
- A gateway that strips `cache_control` does not error. Every turn bills as uncached input. A gateway that rejects the advisor tool gets one retry without it, then Claude Code leaves the advisor off for that base URL until the process exits. Forward `anthropic-beta` and `cache_control` unchanged.
- Turning the advisor off with the env var, or on with `--advisor`, does not by itself invalidate the main prompt cache. The advisor's own read of the transcript is not cached.
- Haiku 5.5 charges more above 100k prompt tokens, and a US-only `inference_geo` multiplies prices by 1.1. `cost_usd_computed` applies neither. Alias prices assume the Anthropic API alias targets. If `model_served` is an id this table does not list, the computed cost is null.
- `tool_calls` is null when `--output-format json` does not include tool-use blocks. The documented result fields used here are `total_cost_usd`, `usage`, `modelUsage`, `num_turns`, `session_id`, `stop_reason`, and `subtype`. `ttft_ms_p50` is always null; time to first token is not in that result.
- Changing model or effort mid-conversation drops the prompt cache. Setup C avoids that by using a new process for the builder, which also starts a new cache.
- Agent runs are noisy. One pass of six tasks is a pilot of the harness, not a leaderboard.

## What was checked against the docs, and what was not

Checked against <https://code.claude.com/docs> and the pricing page while building this repo:

- `claude -p`, `--bare`, `--model`, `--effort`, `--advisor`, `--permission-mode` (`acceptEdits` and `plan`), `--permission-prompts none`, `--allowedTools`, `--output-format json`, `--max-turns`, `--append-system-prompt`, `--settings`
- `CLAUDE_CODE_DISABLE_ADVISOR_TOOL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_EFFORT_LEVEL` (it is applied before `--effort`)
- `plansDirectory`, and plan files living under that directory
- Gateway variables `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_CUSTOM_HEADERS`, and the `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` pins
- Telemetry variables listed above, including cumulative temporality for Prometheus, the cost and token metric names, and `query_source` values `main` / `subagent` / `auxiliary` on those metrics
- `total_cost_usd` and `modelUsage` as client-side estimates; `usage` excluding subagents; `modelUsage` including them
- The advisor staying off when `DISABLE_TELEMETRY` blocks feature flags, and the silent advisor disable when a gateway rejects the advisor tool type
- The unsupported-non-Claude-model statement on the gateway page
- Opus 5.5, Sonnet 5.5, and Haiku 5.5 list prices, including 5-minute writes, 1-hour writes, and cache reads

Not checked by running them here:

- A live `claude` process, a gateway, or the Docker stack. `docker` was not installed in the environment that added this code.
- The exact Prometheus series names after the collector's rename.
- Whether OTel events or `modelUsage` include advisor tokens.
- Whether a headless plan-mode process always leaves a file under `./plans`. The copy step is there so the builder still has something to read when it does.
- Loki's OTLP path. The log pipeline is in the collector config; the query in the latency panel will need a look at one real event.
- Your gateway's fallback rule. The caveat above is the usual contract, not a test against a particular product.

## Phase 2, offline

Once the JSONL exists, label each task with the cheapest setup that passed (lowest summed `cost_usd_computed` among setups with `pass: true`). That label set is enough to score routers **without more coding runs**:

- a fixed rule, such as "always the cheap setup"
- a classifier that sees only the task prompt and predicts easy / medium / hard, mapped onto setups
- a cascade that takes the cheap setup's logged outcome and, on failure, substitutes the baseline setup's logged outcome

Score them with the same cost-per-passing-task definition. The cascade is the coding version of "rerun failures at a higher setting," using tests as the objective check. A classifier trained on someone else's prompts will not transfer; the labels have to come from this task set.

## Tests

```bash
pip install -r requirements.txt
pytest
```

The tests grade the tasks, parse a fake Claude Code result into JSONL, summarize the fake sample, load the setup file, and dry-run the command builder. They do not call a model.
