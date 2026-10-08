"""Run setups against tasks and append JSONL rows."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from bench.commands import (
    build_argv,
    build_prompt,
    child_env,
    format_dry_run,
    write_plan_settings,
)
from bench.config import ROOT, Experiment, Setup, Task
from bench.grade import GradeResult, grade_workspace, prepare_workspace
from bench.records import append_jsonl, extract_json, rows_from_result


def make_run_id(when: datetime, arm: str, task_id: str, repeat: int) -> str:
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{arm}-{task_id}-r{repeat}"


def git_sha(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def claude_version(binary: str) -> str:
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else "unknown"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def default_scratch_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="routing-bench-"))


def run_claude(argv: list[str], cwd: Path, env: dict[str, str], timeout: int):
    """Run one headless Claude Code process. Returns code, stdout, stderr, timed_out."""
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout or "", stderr or "", False
    except subprocess.TimeoutExpired:
        _stop_process_group(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _stop_process_group(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        return proc.returncode if proc.returncode is not None else 124, stdout or "", stderr or "", True


def _stop_process_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return


def materialize_plan(workspace: Path) -> str:
    """Make sure the builder can read PLAN.md.

    Plan mode is documented to write under plansDirectory (./plans here) and
    to block source edits, so PLAN.md may not exist until we copy the plan.
    """
    plan = workspace / "PLAN.md"
    if plan.is_file() and plan.read_text(encoding="utf-8").strip():
        return "planner wrote PLAN.md"
    plans_dir = workspace / "plans"
    files = []
    if plans_dir.is_dir():
        files = [path for path in plans_dir.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime)
    if not files:
        return "no plan file was produced"
    newest = files[-1]
    plan.write_text(newest.read_text(encoding="utf-8"), encoding="utf-8")
    return f"copied {newest.relative_to(workspace)} to PLAN.md"


def _select(
    experiment: Experiment,
    tasks: list[Task],
    *,
    only: set[str] | None,
    task_ids: set[str] | None,
) -> tuple[list[Setup], list[Task]]:
    setups = experiment.setups
    if only:
        setups = [setup for setup in setups if setup.id in only]
        missing = only - {setup.id for setup in setups}
        if missing:
            raise ValueError(f"unknown setup ids: {', '.join(sorted(missing))}")
    chosen = tasks
    if task_ids:
        chosen = [task for task in tasks if task.id in task_ids]
        missing = task_ids - {task.id for task in chosen}
        if missing:
            raise ValueError(f"unknown task ids: {', '.join(sorted(missing))}")
    return setups, chosen


def execute(
    *,
    experiment: Experiment,
    tasks: list[Task],
    prices: dict,
    out_path: Path,
    scratch_root: Path,
    claude_bin: str,
    repeats: int,
    dry_run: bool,
    only: set[str] | None = None,
    task_ids: set[str] | None = None,
    environ: dict[str, str] | None = None,
) -> int:
    parent = os.environ if environ is None else environ
    setups, chosen = _select(experiment, tasks, only=only, task_ids=task_ids)
    scratch_root.mkdir(parents=True, exist_ok=True)
    if _inside(scratch_root, ROOT):
        print(
            "warning: scratch dir is inside the repo; a Bash-capable agent can read "
            "hidden tests and reference solutions. Use a directory outside the repo.",
            file=sys.stderr,
        )
    version = "dry-run" if dry_run else claude_version(claude_bin)
    sha = git_sha(ROOT)
    via_gateway = bool(parent.get("ANTHROPIC_BASE_URL"))
    if not dry_run and any(step.advisor for setup in setups for step in setup.steps):
        if parent.get("DISABLE_TELEMETRY"):
            print(
                "warning: DISABLE_TELEMETRY is set, so Claude Code will not turn "
                "the advisor on. Unset it for setup D.",
                file=sys.stderr,
            )
    invocations = 0
    for setup in setups:
        for task in chosen:
            for repeat in range(1, repeats + 1):
                when = datetime.now(timezone.utc)
                run_id = make_run_id(when, setup.id, task.id, repeat)
                workspace = scratch_root / run_id
                prepare_workspace(task, workspace)
                step_payloads = []
                for index, step in enumerate(setup.steps, start=1):
                    prompt = build_prompt(task.prompt, step)
                    settings = write_plan_settings(workspace) if step.permission_mode == "plan" else None
                    argv = build_argv(claude_bin, step, prompt, settings)
                    meta = {
                        "setup": setup.id,
                        "task": task.id,
                        "role": step.role,
                        "run_id": run_id,
                        "experiment": experiment.experiment,
                    }
                    env = child_env(parent, step, meta)
                    invocations += 1
                    if dry_run:
                        print(f"# dry-run setup={setup.id} task={task.id} repeat={repeat} role={step.role}")
                        print(format_dry_run(argv, env, parent, workspace))
                        print()
                        continue
                    started = datetime.now(timezone.utc)
                    code, stdout, stderr, timed_out = run_claude(
                        argv, workspace, env, step.timeout_seconds
                    )
                    wall_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                    (workspace / f"claude.{index}.{step.role}.stdout").write_text(stdout, encoding="utf-8")
                    (workspace / f"claude.{index}.{step.role}.stderr").write_text(stderr, encoding="utf-8")
                    (workspace / f"claude.{index}.{step.role}.argv").write_text(
                        "\n".join(argv) + "\n", encoding="utf-8"
                    )
                    plan_note = ""
                    if step.role == "planner":
                        plan_note = materialize_plan(workspace)
                    payload = extract_json(stdout)
                    if timed_out:
                        error = f"timeout after {step.timeout_seconds}s"
                    elif payload is None:
                        error = (stderr or stdout or f"exit {code}").strip()[-2000:] or "no json result"
                    elif code not in (0, None):
                        error = (stderr or f"exit {code}").strip()[-2000:] or f"exit {code}"
                    else:
                        error = None
                    step_payloads.append((step, payload, wall_ms, error, plan_note))
                if dry_run:
                    continue
                grade = grade_workspace(task, workspace)
                rows = []
                for step, payload, wall_ms, error, plan_note in step_payloads:
                    context = {
                        "run_id": run_id,
                        "ts": when.astimezone().isoformat(timespec="seconds"),
                        "experiment": experiment.experiment,
                        "arm": setup.id,
                        "task_id": task.id,
                        "difficulty": task.difficulty,
                        "repeat": repeat,
                        "harness_version": version,
                        "via_gateway": via_gateway,
                        "repo_sha": sha,
                        "effort": step.effort,
                        "wall_ms": wall_ms,
                    }
                    rows.extend(
                        rows_from_result(
                            payload,
                            step=step,
                            grade=grade,
                            context=context,
                            prices=prices,
                            error=error,
                            extra_notes=plan_note,
                        )
                    )
                append_jsonl(out_path, rows)
                state = "pass" if grade.passed else "fail"
                print(
                    f"{setup.id} {task.id} r{repeat}: {state} "
                    f"({grade.tests_passed}/{grade.tests_total}) -> {out_path}"
                )
    if dry_run:
        print(f"# dry-run only: {invocations} claude invocation(s), no JSONL written")
    return 0
