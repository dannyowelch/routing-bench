"""Build the Claude Code command line and the environment for one step."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from bench.config import Step

HARNESS_PREAMBLE = """\
You are solving a small coding task in this working directory.
Visible tests are in tests/visible. You may run pytest on that directory.
Hidden tests are applied after you finish. Do not search for them, and do not
edit anything under tests/. Stay inside this directory.
"""

SECRET_HINTS = ("key", "token", "secret", "password", "authorization", "credential")

PLACEHOLDERS = ("setup", "task", "role", "run_id", "experiment")


def build_prompt(task_prompt: str, step: Step) -> str:
    parts = [HARNESS_PREAMBLE.strip(), task_prompt.strip()]
    if step.prompt_suffix.strip():
        parts.append(step.prompt_suffix.strip())
    return "\n\n".join(parts)


def build_argv(
    claude_bin: str,
    step: Step,
    prompt: str,
    settings_path: Path | None,
) -> list[str]:
    argv = [claude_bin]
    if step.bare:
        argv.append("--bare")
    argv.extend(["-p", prompt, "--model", step.model])
    if step.effort:
        argv.extend(["--effort", step.effort])
    argv.extend(
        [
            "--output-format",
            step.output_format,
            "--permission-mode",
            step.permission_mode,
        ]
    )
    if step.permission_prompts:
        argv.extend(["--permission-prompts", step.permission_prompts])
    if step.allowed_tools:
        argv.extend(["--allowedTools", ",".join(step.allowed_tools)])
    if step.max_turns:
        argv.extend(["--max-turns", str(step.max_turns)])
    if step.advisor:
        argv.extend(["--advisor", step.advisor])
    if step.append_system_prompt.strip():
        argv.extend(["--append-system-prompt", step.append_system_prompt.strip()])
    if settings_path is not None:
        argv.extend(["--settings", str(settings_path)])
    return argv


def write_plan_settings(workspace: Path) -> Path:
    """Point plan mode at ./plans inside the scratch workspace."""
    path = workspace / ".bench-settings.json"
    path.write_text(
        json.dumps({"plansDirectory": "./plans"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def render_placeholders(template: str, meta: dict[str, str]) -> str:
    text = template.replace("\\n", "\n")
    for key in PLACEHOLDERS:
        text = text.replace("{" + key + "}", meta.get(key, ""))
    return text


def parse_header_lines(block: str) -> list[tuple[str, str]]:
    headers = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        name, value = stripped.split(":", 1)
        headers.append((name.strip(), value.strip()))
    return headers


def merge_custom_headers(existing: str, extra: list[tuple[str, str]]) -> str:
    """Append benchmark headers. An extra header replaces one of the same name."""
    current = parse_header_lines(existing)
    replaced = {name.lower() for name, _value in extra}
    kept = [(name, value) for name, value in current if name.lower() not in replaced]
    lines = [f"{name}: {value}" for name, value in kept + extra]
    return "\n".join(lines)


def gateway_headers(parent: dict[str, str], meta: dict[str, str]) -> list[tuple[str, str]]:
    template = parent.get("BENCHMARK_GATEWAY_HEADERS", "").strip()
    if not template or template.lower() == "off":
        return []
    return parse_header_lines(render_placeholders(template, meta))


def _looks_secret(name: str) -> bool:
    lowered = name.lower().replace("_", "-")
    return any(hint in lowered for hint in SECRET_HINTS)


def redact_headers(block: str) -> str:
    redacted = []
    for name, value in parse_header_lines(block):
        shown = "***" if _looks_secret(name) else value
        redacted.append(f"{name}: {shown}")
    return "\n".join(redacted)


def merge_resource_attributes(existing: str, meta: dict[str, str]) -> str:
    """Merge OTEL_RESOURCE_ATTRIBUTES. Run labels replace earlier ones."""
    pairs: list[tuple[str, str]] = []
    for part in existing.split(","):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        pairs.append((key.strip(), value.strip()))
    labels = {
        "experiment": meta["experiment"],
        "setup": meta["setup"],
        "task": meta["task"],
        "role": meta["role"],
        "run_id": meta["run_id"],
    }
    replaced = set(labels)
    kept = [(key, value) for key, value in pairs if key not in replaced]
    for key, value in labels.items():
        if any(token in value for token in ",= "):
            raise ValueError(f"resource attribute {key} contains a reserved character")
    ordered = kept + list(labels.items())
    return ",".join(f"{key}={value}" for key, value in ordered)


def child_env(parent: dict[str, str], step: Step, meta: dict[str, str]) -> dict[str, str]:
    """Environment for one Claude Code process.

    Effort and the subagent model are set here because those variables win
    over flags and saved settings. A saved advisor is turned off with
    CLAUDE_CODE_DISABLE_ADVISOR_TOOL unless this step asked for one.
    """
    env = dict(parent)
    if step.effort:
        env["CLAUDE_CODE_EFFORT_LEVEL"] = step.effort
    if step.advisor:
        env.pop("CLAUDE_CODE_DISABLE_ADVISOR_TOOL", None)
    else:
        env["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"] = "1"
    if step.subagent_model:
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = step.subagent_model
    else:
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)

    extra = gateway_headers(parent, meta)
    merged = merge_custom_headers(env.get("ANTHROPIC_CUSTOM_HEADERS", ""), extra)
    if merged:
        env["ANTHROPIC_CUSTOM_HEADERS"] = merged
    else:
        env.pop("ANTHROPIC_CUSTOM_HEADERS", None)

    if env.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1":
        env["OTEL_RESOURCE_ATTRIBUTES"] = merge_resource_attributes(
            env.get("OTEL_RESOURCE_ATTRIBUTES", ""),
            meta,
        )
    return env


def format_dry_run(argv: list[str], env: dict[str, str], parent: dict[str, str], cwd: Path) -> str:
    """Shell-quoted command plus the variables this step changed, secrets redacted."""
    interesting = [
        "CLAUDE_CODE_EFFORT_LEVEL",
        "CLAUDE_CODE_DISABLE_ADVISOR_TOOL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "ANTHROPIC_CUSTOM_HEADERS",
        "OTEL_RESOURCE_ATTRIBUTES",
        "CLAUDE_CODE_ENABLE_TELEMETRY",
    ]
    lines = [f"cd {shlex.quote(str(cwd))}"]
    for key in interesting:
        if key not in env:
            if key in parent:
                lines.append(f"unset {key}")
            continue
        if env.get(key) == parent.get(key) and key != "ANTHROPIC_CUSTOM_HEADERS":
            continue
        value = env[key]
        if key == "ANTHROPIC_CUSTOM_HEADERS":
            value = redact_headers(value)
        elif _looks_secret(key):
            value = "***"
        shown = value.replace("\n", "\\n")
        lines.append(f"export {key}={shlex.quote(shown)}")
    lines.append(shlex.join(argv))
    return "\n".join(lines)
