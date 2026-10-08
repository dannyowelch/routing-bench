"""Turn one Claude Code JSON result into JSONL rows."""

from __future__ import annotations

import json
from pathlib import Path

from bench.commands import Step
from bench.cost import compute_cost_usd, find_price
from bench.grade import GradeResult

ROW_KEYS = [
    "schema",
    "run_id",
    "ts",
    "experiment",
    "arm",
    "task_id",
    "difficulty",
    "repeat",
    "attempt",
    "harness",
    "harness_version",
    "via_gateway",
    "repo_sha",
    "role",
    "query_source",
    "agent_type",
    "model_requested",
    "model_served",
    "effort",
    "input_uncached",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "output",
    "advisor_calls",
    "turns",
    "tool_calls",
    "subagents",
    "cost_usd_client",
    "cost_usd_gateway",
    "cost_usd_computed",
    "price_table",
    "wall_ms",
    "ttft_ms_p50",
    "gate",
    "pass",
    "tests_passed",
    "tests_total",
    "stop_reason",
    "error",
    "notes",
]


def extract_json(stdout: str) -> dict | None:
    """Parse a --output-format json payload, even with a warning line before it."""
    text = stdout.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return data
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _first(mapping: dict, *keys):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def walk_tool_uses(node) -> list[str]:
    """Collect tool names from any tool_use blocks present in the payload."""
    found = []
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and node.get("name"):
            found.append(str(node["name"]))
        for value in node.values():
            found.extend(walk_tool_uses(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_tool_uses(item))
    return found


def cache_split(usage: dict) -> tuple[int | None, int | None]:
    """Return (5m, 1h) cache-write tokens when the result splits them."""
    creation = usage.get("cache_creation")
    if not isinstance(creation, dict):
        return None, None
    five = _int(creation.get("ephemeral_5m_input_tokens"))
    hour = _int(creation.get("ephemeral_1h_input_tokens"))
    if five is None and hour is None:
        return None, None
    return five or 0, hour or 0


def _same_model(served: str, requested: str | None) -> bool:
    if not requested:
        return False
    left = served.lower()
    right = requested.lower()
    return left == right or right in left or left in right


def _role_for(served: str, step: Step) -> tuple[str, str | None]:
    if step.advisor and _same_model(served, step.advisor) and not _same_model(served, step.model):
        # The monitoring docs do not list an advisor query_source.
        return "advisor", None
    if (
        step.subagent_model
        and _same_model(served, step.subagent_model)
        and not _same_model(served, step.model)
    ):
        return "subagent", "subagent"
    query = "main" if step.role in {"planner", "builder"} else None
    return step.role, query


def _usage_tokens(block: dict) -> dict[str, int]:
    return {
        "input_uncached": _int(_first(block, "input_tokens", "inputTokens")) or 0,
        "cache_read": _int(_first(block, "cache_read_input_tokens", "cacheReadInputTokens")) or 0,
        "cache_write": _int(
            _first(block, "cache_creation_input_tokens", "cacheCreationInputTokens")
        )
        or 0,
        "output": _int(_first(block, "output_tokens", "outputTokens")) or 0,
    }


def _blank(context: dict) -> dict:
    row = {key: None for key in ROW_KEYS}
    row.update(
        {
            "schema": "routing-v1",
            "run_id": context["run_id"],
            "ts": context["ts"],
            "experiment": context["experiment"],
            "arm": context["arm"],
            "task_id": context["task_id"],
            "difficulty": context["difficulty"],
            "repeat": context["repeat"],
            "attempt": 1,
            "harness": "claude-code",
            "harness_version": context["harness_version"],
            "via_gateway": context["via_gateway"],
            "repo_sha": context["repo_sha"],
            "agent_type": None,
            "effort": context["effort"],
            "subagents": None,
            "cost_usd_gateway": None,
            "ttft_ms_p50": None,
            "gate": "pytest-hidden",
            "notes": "",
        }
    )
    return row


def _apply_grade(row: dict, grade: GradeResult) -> None:
    row["pass"] = grade.passed
    row["tests_passed"] = grade.tests_passed
    row["tests_total"] = grade.tests_total


def _note(row: dict, text: str) -> None:
    if not text:
        return
    row["notes"] = (row["notes"] + " " + text).strip() if row["notes"] else text


def rows_from_result(
    payload: dict | None,
    *,
    step: Step,
    grade: GradeResult,
    context: dict,
    prices: dict,
    error: str | None,
    extra_notes: str = "",
) -> list[dict]:
    """One row per served model when the result breaks usage down that way."""
    tool_names = walk_tool_uses(payload) if payload else []
    advisor_calls = None
    tool_calls = None
    if payload is not None and tool_names:
        tool_calls = len(tool_names)
        advisor_calls = sum(1 for name in tool_names if name.lower() == "advisor")
    elif payload is not None:
        # The json result documents num_turns, not a tool-call count.
        advisor_calls = None
        tool_calls = None

    turns = _int(payload.get("num_turns")) if payload else None
    stop = None
    if payload:
        stop = payload.get("stop_reason") or payload.get("subtype")

    model_usage = None
    if payload:
        model_usage = payload.get("modelUsage") or payload.get("model_usage")
    usage = payload.get("usage") if payload else None
    if not isinstance(usage, dict):
        usage = {}

    slices: list[tuple[str, dict, float | None]] = []
    if isinstance(model_usage, dict) and model_usage:
        for served, block in model_usage.items():
            if not isinstance(block, dict):
                continue
            client = block.get("costUSD", block.get("cost_usd"))
            slices.append((str(served), _usage_tokens(block), client))
    if not slices:
        served = step.model
        tokens = _usage_tokens(usage) if usage else {
            "input_uncached": 0,
            "cache_read": 0,
            "cache_write": 0,
            "output": 0,
        }
        client = payload.get("total_cost_usd") if payload else None
        if payload is None:
            tokens = {key: None for key in tokens}
        slices.append((served, tokens, client))

    five, hour = cache_split(usage)
    single = len(slices) == 1 and slices[0][1].get("cache_write") is not None
    rows = []
    primary_index = 0
    for index, (served, _tokens, _client) in enumerate(slices):
        role, _query = _role_for(served, step)
        if role == step.role:
            primary_index = index
            break

    for index, (served, tokens, client) in enumerate(slices):
        role, query_source = _role_for(served, step)
        requested = step.model
        if role == "advisor":
            requested = step.advisor
        elif role == "subagent":
            requested = step.subagent_model
        row = _blank(context)
        row["role"] = role
        row["query_source"] = query_source
        row["model_requested"] = requested
        row["model_served"] = served
        write_5m = tokens.get("cache_write")
        write_1h = 0 if write_5m is not None else None
        notes = []
        if (
            single
            and five is not None
            and hour is not None
            and (five + hour) == tokens.get("cache_write")
        ):
            write_5m, write_1h = five, hour
        elif write_5m:
            notes.append(
                "cache write TTL was not split in this result; counted as cache_write_5m"
            )
        row["input_uncached"] = tokens.get("input_uncached")
        row["cache_read"] = tokens.get("cache_read")
        row["cache_write_5m"] = write_5m
        row["cache_write_1h"] = write_1h
        row["output"] = tokens.get("output")
        row["cost_usd_client"] = client
        if all(tokens.get(key) is not None for key in ("input_uncached", "cache_read", "output")):
            priced_model = served or requested
            row["cost_usd_computed"] = compute_cost_usd(
                priced_model,
                input_uncached=tokens["input_uncached"],
                cache_read=tokens["cache_read"],
                cache_write_5m=write_5m or 0,
                cache_write_1h=write_1h or 0,
                output=tokens["output"],
                table=prices,
            )
            if find_price(priced_model, prices) is None:
                notes.append(f"no price table row for model {priced_model}")
            elif "haiku" in (priced_model or "").lower():
                total_in = (
                    tokens["input_uncached"]
                    + tokens["cache_read"]
                    + (write_5m or 0)
                    + (write_1h or 0)
                )
                if total_in > 100_000:
                    notes.append(
                        "aggregate input exceeds 100000 tokens; Haiku long-context tier was not applied"
                    )
        row["price_table"] = prices.get("id")
        is_primary = index == primary_index
        if is_primary:
            row["wall_ms"] = context["wall_ms"]
            row["turns"] = turns
            row["tool_calls"] = tool_calls
            row["advisor_calls"] = advisor_calls
        row["stop_reason"] = stop if is_primary else None
        row["error"] = error if is_primary else None
        _apply_grade(row, grade)
        for note in notes:
            _note(row, note)
        if extra_notes and is_primary:
            _note(row, extra_notes)
        if payload and payload.get("session_id") and is_primary:
            _note(row, f"session_id={payload['session_id']}")
        rows.append({key: row[key] for key in ROW_KEYS})
    if step.advisor and rows and all(row["role"] != "advisor" for row in rows):
        for row in rows:
            if row["role"] == step.role:
                _note(
                    row,
                    "advisor was enabled but modelUsage had no separate advisor model; "
                    "advisor tokens are not broken out in the Claude Code docs",
                )
                break
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            missing = [key for key in ROW_KEYS if key not in row]
            if missing:
                raise ValueError(f"row missing {missing}")
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
