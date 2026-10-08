"""Load setups, tasks, and the price table."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

_PLACEHOLDER = __import__("re").compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}"
)


def expand_value(value, environ: dict[str, str] | None = None):
    """Expand ${VAR} and ${VAR:-default} strings. Other types pass through."""
    environ = os.environ if environ is None else environ
    if isinstance(value, str):
        def repl(match):
            name, default = match.group(1), match.group(2)
            current = environ.get(name)
            if current:
                return current
            if default is not None:
                return default
            raise KeyError(f"environment variable {name} is not set")

        return _PLACEHOLDER.sub(repl, value)
    if isinstance(value, list):
        return [expand_value(item, environ) for item in value]
    if isinstance(value, dict):
        return {key: expand_value(item, environ) for key, item in value.items()}
    return value


def load_yaml(path: Path, environ: dict[str, str] | None = None):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return expand_value(data, environ)


@dataclass
class Step:
    role: str
    model: str
    effort: str | None
    advisor: str | None
    subagent_model: str | None
    permission_mode: str
    permission_prompts: str | None
    allowed_tools: list[str]
    timeout_seconds: int
    max_turns: int
    bare: bool
    output_format: str
    append_system_prompt: str
    prompt_suffix: str


@dataclass
class Setup:
    id: str
    label: str
    description: str
    steps: list[Step] = field(default_factory=list)


@dataclass
class Experiment:
    schema: str
    experiment: str
    setups: list[Setup]


def _disabled_model(value) -> str | None:
    """Map off/inherit/none to 'not set' for advisor and subagent model fields.

    YAML 1.1 reads an unquoted ``off`` as boolean false, so false is off too.
    """
    if value is None or value is False:
        return None
    if value is True:
        raise ValueError("advisor or subagent_model is 'on' but needs a model id")
    text = str(value).strip()
    if text.lower() in {"", "off", "none", "inherit", "false"}:
        return None
    return text


def _optional_flag(value) -> str | None:
    """Keep a flag value such as permission-prompts 'none'. Blank or off omits it."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "off"}:
        return None
    return text


def load_experiment(path: Path, environ: dict[str, str] | None = None) -> Experiment:
    raw = load_yaml(path, environ)
    defaults = raw.get("defaults") or {}
    setups = []
    for setup_id, body in (raw.get("setups") or {}).items():
        steps = []
        for step in body.get("steps") or []:
            merged = {**defaults, **step}
            role = merged.get("role")
            if role not in {"planner", "builder"}:
                raise ValueError(f"setup {setup_id} has unsupported role {role!r}")
            model = merged.get("model")
            if not model:
                raise ValueError(f"setup {setup_id} step {role} needs a model")
            subagent = merged.get("subagent_model", "inherit")
            advisor = merged.get("advisor", "off")
            steps.append(
                Step(
                    role=role,
                    model=str(model),
                    effort=(None if not merged.get("effort") else str(merged["effort"])),
                    advisor=_disabled_model(advisor),
                    subagent_model=_disabled_model(subagent),
                    permission_mode=str(merged.get("permission_mode") or "acceptEdits"),
                    permission_prompts=_optional_flag(merged.get("permission_prompts")),
                    allowed_tools=list(merged.get("allowed_tools") or []),
                    timeout_seconds=int(merged.get("timeout_seconds") or 900),
                    max_turns=int(merged.get("max_turns") or 40),
                    bare=bool(merged.get("bare", True)),
                    output_format=str(merged.get("output_format") or "json"),
                    append_system_prompt=str(merged.get("append_system_prompt") or ""),
                    prompt_suffix=str(merged.get("prompt_suffix") or ""),
                )
            )
        if not steps:
            raise ValueError(f"setup {setup_id} has no steps")
        setups.append(
            Setup(
                id=str(setup_id),
                label=str(body.get("label") or setup_id),
                description=str(body.get("description") or "").strip(),
                steps=steps,
            )
        )
    if not setups:
        raise ValueError(f"no setups in {path}")
    return Experiment(
        schema=str(raw.get("schema") or "routing-v1"),
        experiment=str(raw.get("experiment") or "routing-v1"),
        setups=setups,
    )


@dataclass
class Task:
    id: str
    title: str
    difficulty: str
    root: Path
    prompt: str

    @property
    def starter(self) -> Path:
        return self.root / "starter"

    @property
    def hidden_tests(self) -> Path:
        return self.root / "hidden_tests"

    @property
    def visible_tests(self) -> Path:
        return self.root / "visible_tests"


def load_tasks(root: Path) -> list[Task]:
    tasks = []
    if not root.is_dir():
        raise ValueError(f"task directory not found: {root}")
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        meta_path = path / "task.yaml"
        if not meta_path.exists():
            continue
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        task_id = str(meta.get("id") or path.name)
        prompt_path = path / "prompt.md"
        if not prompt_path.exists():
            raise ValueError(f"{path} is missing prompt.md")
        hidden = list((path / "hidden_tests").glob("test_*.py"))
        visible = list((path / "visible_tests").glob("test_*.py"))
        if not hidden:
            raise ValueError(f"{path} has no hidden tests")
        if not visible:
            raise ValueError(f"{path} has no visible tests")
        if not (path / "starter").is_dir():
            raise ValueError(f"{path} is missing starter/")
        tasks.append(
            Task(
                id=task_id,
                title=str(meta.get("title") or task_id),
                difficulty=str(meta.get("difficulty") or "unknown"),
                root=path,
                prompt=prompt_path.read_text(encoding="utf-8").strip(),
            )
        )
    tasks.sort(key=lambda task: task.id)
    if not tasks:
        raise ValueError(f"no tasks under {root}")
    return tasks


def load_prices(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "models" not in data:
        raise ValueError(f"{path} has no models")
    return data


def load_dotenv(path: Path, environ: dict[str, str] | None = None) -> None:
    """Set variables from a .env file. Existing values win. Missing file is fine."""
    target = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in target:
            target[key] = value
