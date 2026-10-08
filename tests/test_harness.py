"""Unit tests for the harness. No model calls."""

import json
import shutil
from pathlib import Path

import pytest

from bench.commands import build_argv, child_env, format_dry_run
from bench.config import ROOT, load_experiment, load_prices, load_tasks
from bench.cost import compute_cost_usd
from bench.grade import grade_workspace, prepare_workspace
from bench.records import ROW_KEYS, append_jsonl, extract_json, rows_from_result
from bench.runner import execute
from analyze import summarize

PRICES = load_prices(ROOT / "prices.yaml")


def _grade_stub(passed=True):
    from bench.grade import GradeResult

    return GradeResult(passed, 3 if passed else 1, 3, None if passed else "failed")


def _context(**overrides):
    base = {
        "run_id": "run-1",
        "ts": "2026-10-08T00:00:00+00:00",
        "experiment": "routing-v1",
        "arm": "A",
        "task_id": "t1",
        "difficulty": "easy",
        "repeat": 1,
        "harness_version": "test",
        "via_gateway": False,
        "repo_sha": "abc",
        "effort": "medium",
        "wall_ms": 1000,
    }
    base.update(overrides)
    return base


def test_example_setups_cover_a_through_f():
    experiment = load_experiment(
        ROOT / "setups.example.yaml",
        environ={"MODEL_MID": "mid-from-env"},
    )
    by_id = {setup.id: setup for setup in experiment.setups}
    assert list(by_id) == ["A", "B", "C", "D", "E", "F"]
    assert by_id["A"].steps[0].model == "mid-from-env"
    assert by_id["B"].steps[0].model == "haiku"
    assert [step.role for step in by_id["C"].steps] == ["planner", "builder"]
    assert by_id["C"].steps[0].permission_mode == "plan"
    assert by_id["C"].steps[1].model == "haiku"
    assert by_id["D"].steps[0].advisor == "opus"
    assert by_id["D"].steps[0].permission_prompts == "none"
    assert by_id["E"].steps[0].subagent_model == "haiku"
    assert by_id["F"].steps[0].effort == "low"
    assert by_id["F"].steps[0].model == "opus"


def test_tasks_load_with_hidden_tests_outside_starter():
    tasks = load_tasks(ROOT / "tasks")
    assert [task.id for task in tasks] == ["t1", "t2", "t3", "t4", "t5", "t6"]
    difficulties = [task.difficulty for task in tasks]
    assert difficulties.count("easy") == 2
    assert difficulties.count("medium") == 2
    assert difficulties.count("hard") == 2
    for task in tasks:
        hidden = {path.name for path in task.hidden_tests.glob("test_*.py")}
        starter_files = {path.name for path in task.starter.rglob("*") if path.is_file()}
        assert hidden
        assert hidden.isdisjoint(starter_files)


def test_prepare_workspace_omits_hidden_tests(tmp_path):
    task = load_tasks(ROOT / "tasks")[0]
    dest = tmp_path / "work"
    prepare_workspace(task, dest)
    assert (dest / "stats.py").is_file()
    assert (dest / "tests" / "visible" / "test_visible.py").is_file()
    assert not (dest / "tests" / "hidden").exists()
    assert "hidden_tests" not in {path.name for path in dest.rglob("*")}


def test_price_table_matches_families_and_not_older_ids():
    million = 1_000_000
    assert compute_cost_usd(
        "haiku",
        input_uncached=million,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=0,
        output=0,
        table=PRICES,
    ) == pytest.approx(0.10)
    assert compute_cost_usd(
        "claude-sonnet-5-5",
        input_uncached=0,
        cache_read=million,
        cache_write_5m=0,
        cache_write_1h=0,
        output=0,
        table=PRICES,
    ) == pytest.approx(0.10)
    assert compute_cost_usd(
        "claude-opus-5-5",
        input_uncached=0,
        cache_read=0,
        cache_write_5m=0,
        cache_write_1h=million,
        output=0,
        table=PRICES,
    ) == pytest.approx(8)
    assert (
        compute_cost_usd(
            "claude-haiku-4-5",
            input_uncached=10,
            cache_read=0,
            cache_write_5m=0,
            cache_write_1h=0,
            output=0,
            table=PRICES,
        )
        is None
    )


def test_command_flags_and_env_isolation():
    experiment = load_experiment(ROOT / "setups.example.yaml", environ={})
    by_id = {setup.id: setup for setup in experiment.setups}
    builder = by_id["A"].steps[0]
    argv = build_argv("claude", builder, "fix the bug", None)
    assert "--bare" in argv
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--advisor" not in argv

    advisor = by_id["D"].steps[0]
    advisor_argv = build_argv("claude", advisor, "fix the bug", None)
    assert advisor_argv[advisor_argv.index("--advisor") + 1] == "opus"
    assert "--append-system-prompt" in advisor_argv

    parent = {
        "CLAUDE_CODE_SUBAGENT_MODEL": "opus",
        "ANTHROPIC_CUSTOM_HEADERS": "X-Api-Key: supersecret",
        "BENCHMARK_GATEWAY_HEADERS": "X-Benchmark-Setup: {setup}\\nX-Benchmark-Role: {role}",
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_RESOURCE_ATTRIBUTES": "team=local",
    }
    env = child_env(parent, builder, {
        "setup": "A",
        "task": "t1",
        "role": "builder",
        "run_id": "run-1",
        "experiment": "routing-v1",
    })
    assert env["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"] == "1"
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in env
    assert "X-Api-Key: supersecret" in env["ANTHROPIC_CUSTOM_HEADERS"]
    assert "X-Benchmark-Setup: A" in env["ANTHROPIC_CUSTOM_HEADERS"]
    assert "X-Benchmark-Role: builder" in env["ANTHROPIC_CUSTOM_HEADERS"]
    assert "setup=A" in env["OTEL_RESOURCE_ATTRIBUTES"]
    assert "team=local" in env["OTEL_RESOURCE_ATTRIBUTES"]

    cheap_subs = by_id["E"].steps[0]
    sub_env = child_env(parent, cheap_subs, {
        "setup": "E",
        "task": "t1",
        "role": "builder",
        "run_id": "run-e",
        "experiment": "routing-v1",
    })
    assert sub_env["CLAUDE_CODE_SUBAGENT_MODEL"] == "haiku"

    shown = format_dry_run(argv, env, parent, Path("/tmp/scratch"))
    assert "supersecret" not in shown
    assert "***" in shown
    assert "claude --bare -p" in shown


def test_jsonl_rows_split_by_model_and_round_trip(tmp_path):
    experiment = load_experiment(ROOT / "setups.example.yaml", environ={})
    step = {setup.id: setup for setup in experiment.setups}["D"].steps[0]
    payload = {
        "subtype": "success",
        "session_id": "sess-1",
        "num_turns": 6,
        "stop_reason": "end_turn",
        "total_cost_usd": 0.51,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "modelUsage": {
            "claude-haiku-5-5": {
                "inputTokens": 10,
                "outputTokens": 5,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
                "costUSD": 0.01,
            },
            "claude-opus-5-5": {
                "inputTokens": 100,
                "outputTokens": 10,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 40,
                "costUSD": 0.5,
            },
        },
        "messages": [
            {"content": [{"type": "tool_use", "name": "advisor"}]},
            {"content": [{"type": "tool_use", "name": "Bash"}]},
        ],
    }
    rows = rows_from_result(
        payload,
        step=step,
        grade=_grade_stub(),
        context=_context(arm="D", effort="medium"),
        prices=PRICES,
        error=None,
    )
    roles = {row["role"] for row in rows}
    assert roles == {"builder", "advisor"}
    builder = next(row for row in rows if row["role"] == "builder")
    advisor = next(row for row in rows if row["role"] == "advisor")
    assert builder["wall_ms"] == 1000
    assert advisor["wall_ms"] is None
    assert builder["advisor_calls"] == 1
    assert builder["tool_calls"] == 2
    assert builder["turns"] == 6
    assert advisor["query_source"] is None
    assert builder["query_source"] == "main"
    assert builder["cost_usd_computed"] == pytest.approx((10 * 0.10 + 5 * 0.50) / 1_000_000)
    assert advisor["cost_usd_computed"] == pytest.approx((100 * 4 + 40 * 5 + 10 * 20) / 1_000_000)
    assert set(builder) == set(ROW_KEYS)
    path = tmp_path / "runs.jsonl"
    append_jsonl(path, rows)
    append_jsonl(path, rows)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert json.loads(lines[0])["arm"] == "D"


def test_cache_split_used_for_a_single_model():
    experiment = load_experiment(ROOT / "setups.example.yaml", environ={})
    step = experiment.setups[0].steps[0]
    payload = {
        "num_turns": 2,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 30,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 20,
                "ephemeral_1h_input_tokens": 10,
            },
        },
        "modelUsage": {
            "claude-sonnet-5-5": {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 50,
                "cacheCreationInputTokens": 30,
                "costUSD": 0.2,
            }
        },
    }
    rows = rows_from_result(
        payload,
        step=step,
        grade=_grade_stub(),
        context=_context(),
        prices=PRICES,
        error=None,
    )
    assert len(rows) == 1
    assert rows[0]["cache_write_5m"] == 20
    assert rows[0]["cache_write_1h"] == 10
    assert rows[0]["tool_calls"] is None
    assert rows[0]["advisor_calls"] is None
    expected = (100 * 2 + 50 * 0.10 + 20 * 2.50 + 10 * 4 + 20 * 10) / 1_000_000
    assert rows[0]["cost_usd_computed"] == pytest.approx(expected)


def test_extract_json_skips_a_warning_line():
    payload = extract_json('warning: something\n{"total_cost_usd": 1, "num_turns": 2}\n')
    assert payload["num_turns"] == 2


def test_failed_launch_still_writes_a_row():
    experiment = load_experiment(ROOT / "setups.example.yaml", environ={})
    rows = rows_from_result(
        None,
        step=experiment.setups[0].steps[0],
        grade=_grade_stub(False),
        context=_context(),
        prices=PRICES,
        error="timeout after 900s",
    )
    assert rows[0]["pass"] is False
    assert rows[0]["error"] == "timeout after 900s"
    assert rows[0]["cost_usd_computed"] is None


def _apply_reference(task, dest: Path):
    reference = ROOT / "tests" / "reference_solutions" / task.id
    for path in reference.rglob("*"):
        if path.is_file():
            target = dest / path.relative_to(reference)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, target)


def test_each_task_fails_on_starter_and_passes_on_reference(tmp_path):
    for task in load_tasks(ROOT / "tasks"):
        starter = tmp_path / f"{task.id}-starter"
        prepare_workspace(task, starter)
        starter_grade = grade_workspace(task, starter)
        assert starter_grade.passed is False, task.id
        solved = tmp_path / f"{task.id}-solved"
        prepare_workspace(task, solved)
        _apply_reference(task, solved)
        solved_grade = grade_workspace(task, solved)
        assert solved_grade.passed is True, (task.id, solved_grade.error)
        fresh = tmp_path / f"{task.id}-fresh"
        prepare_workspace(task, fresh)
        assert not (fresh / "tests" / "hidden").exists()


def test_dry_run_prints_commands_and_does_not_spawn(tmp_path, monkeypatch, capsys):
    def explode(*_args, **_kwargs):
        raise AssertionError("claude was started")

    monkeypatch.setattr("bench.runner.run_claude", explode)
    experiment = load_experiment(ROOT / "setups.example.yaml", environ={})
    tasks = load_tasks(ROOT / "tasks")[:1]
    code = execute(
        experiment=experiment,
        tasks=tasks,
        prices=PRICES,
        out_path=tmp_path / "out.jsonl",
        scratch_root=tmp_path / "scratch",
        claude_bin="claude",
        repeats=1,
        dry_run=True,
        environ={},
    )
    assert code == 0
    assert not (tmp_path / "out.jsonl").exists()
    printed = capsys.readouterr().out
    assert printed.count("dry-run setup=") == 7
    assert "--permission-mode plan" in printed
    assert "--advisor opus" in printed
    assert "--effort low" in printed
    assert "mean_inclusive" in printed


def test_analyzer_on_fake_sample():
    from analyze import load_jsonl

    rows = load_jsonl(ROOT / "samples" / "FAKE_example_results.jsonl")
    summaries = {item["setup"]: item for item in summarize(rows)}
    assert summaries["A"]["runs"] == 2
    assert summaries["A"]["pass_rate"] == pytest.approx(0.5)
    assert summaries["A"]["mean_cost_usd"] == pytest.approx(0.20)
    assert summaries["A"]["cost_per_passing_task_usd"] == pytest.approx(0.40)
    assert summaries["A"]["mean_latency_ms"] == pytest.approx(150000)
    assert summaries["A"]["cache_hit_ratio"] == pytest.approx(0.4)
    assert summaries["C"]["runs"] == 1
    assert summaries["C"]["pass_rate"] == pytest.approx(1)
    assert summaries["C"]["mean_cost_usd"] == pytest.approx(0.12)
    assert summaries["C"]["cost_per_passing_task_usd"] == pytest.approx(0.12)
    assert summaries["C"]["mean_latency_ms"] == pytest.approx(12000)
    assert summaries["C"]["cache_hit_ratio"] == pytest.approx(0.625)
    assert summaries["D"]["consult_rate"] == pytest.approx(1)
    assert summaries["A"]["consult_rate"] == pytest.approx(0)
