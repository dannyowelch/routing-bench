"""Copy a task into a scratch workspace and grade it with hidden tests."""

from __future__ import annotations

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from bench.config import Task


@dataclass
class GradeResult:
    passed: bool
    tests_passed: int
    tests_total: int
    error: str | None


def prepare_workspace(task: Task, dest: Path) -> None:
    """Copy starter code and visible tests. Hidden tests stay out."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task.starter, dest)
    hidden = dest / "tests" / "hidden"
    if hidden.exists():
        shutil.rmtree(hidden)
    visible = dest / "tests" / "visible"
    if visible.exists():
        shutil.rmtree(visible)
    shutil.copytree(task.visible_tests, visible)


def _refresh_tests(task: Task, dest: Path) -> None:
    """Install the canonical tests, replacing anything the agent edited."""
    for name, source in (
        ("visible", task.visible_tests),
        ("hidden", task.hidden_tests),
    ):
        target = dest / "tests" / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)


def _parse_junit(path: Path) -> tuple[int, int, int, int]:
    root = ET.parse(path).getroot()
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
    tests = failures = errors = skipped = 0
    for suite in suites:
        tests += int(suite.attrib.get("tests", 0))
        failures += int(suite.attrib.get("failures", 0))
        errors += int(suite.attrib.get("errors", 0))
        skipped += int(suite.attrib.get("skipped", 0))
    return tests, failures, errors, skipped


def grade_workspace(task: Task, dest: Path) -> GradeResult:
    _refresh_tests(task, dest)
    # A config file in the scratch dir stops pytest from adopting the harness
    # project's pyproject.toml when the scratch directory lives inside the repo.
    (dest / "pytest.ini").write_text("[pytest]\naddopts =\n", encoding="utf-8")
    report = dest / ".grade-junit.xml"
    if report.exists():
        report.unlink()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/visible",
            "tests/hidden",
            "--rootdir",
            str(dest),
            "-c",
            str(dest / "pytest.ini"),
            "--junitxml",
            str(report),
            "-q",
            "--tb=line",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    if not report.exists():
        detail = (proc.stderr or proc.stdout or "pytest produced no report").strip()
        return GradeResult(False, 0, 0, detail[-2000:])
    tests, failures, errors, skipped = _parse_junit(report)
    passed_count = tests - failures - errors - skipped
    ok = tests > 0 and failures == 0 and errors == 0
    error = None
    if not ok:
        detail = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        error = detail.strip()[-2000:] or "tests failed"
    return GradeResult(ok, max(passed_count, 0), tests, error)
