"""Run the test suite and render an automated testing report.

Uses pytest's built-in JUnit XML output, so there is no extra dependency, and
renders a Markdown report with the totals, the execution time and the per-case
results grouped by the area each file covers.

    python scripts/test_report.py                   # report to stdout
    python scripts/test_report.py --output TEST_REPORT.md
    python scripts/test_report.py --quiet           # just the summary table

Exits non-zero when any test failed, so it is usable as a CI gate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: What each test module covers, for the grouped report.
AREAS: dict[str, str] = {
    "test_pricing_engine": "Pricing engine (pure arithmetic)",
    "test_discount_engine": "Discount rule engine (pure policy)",
    "test_state_machine": "Request state machine and money helpers",
    "test_workflow_boundaries": "Workflow boundaries (retries, gate, no-op, escalation, budget)",
    "test_failure_handling": "Failure handling and idempotency",
    "test_master_data_requests": "Master-data authorisation (manager approval)",
    "test_end_to_end_scenarios": "End-to-end demonstration scenarios",
    "test_security": "Security (auth, RBAC, passwords, downloads, config)",
    "test_workflow": "Workflow pipeline",
    "test_approvals": "Manager approvals",
    "test_quotations": "Quotations, PDF and verification",
    "test_catalogue": "Catalogue, products and customers",
    "test_auth": "Authentication and access control",
    "test_analytics_and_audit": "Analytics, audit trail and settings",
}


@dataclass
class Case:
    name: str
    classname: str
    time: float
    status: str  # passed | failed | error | skipped
    message: str = ""

    @property
    def module(self) -> str:
        """`tests.test_workflow` or `tests.test_workflow.TestClass` -> module."""
        parts = self.classname.split(".")
        for part in parts:
            if part.startswith("test_"):
                return part
        return parts[-1] if parts else "unknown"

    @property
    def group(self) -> str:
        """The class name within the module, when the test lives in one."""
        parts = self.classname.split(".")
        return parts[-1] if parts and not parts[-1].startswith("test_") else ""


@dataclass
class Suite:
    cases: list[Case] = field(default_factory=list)
    duration: float = 0.0

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if case.status in {"failed", "error"})

    @property
    def skipped(self) -> int:
        return sum(1 for case in self.cases if case.status == "skipped")

    @property
    def pass_rate(self) -> float:
        runnable = self.total - self.skipped
        return (self.passed / runnable * 100) if runnable else 0.0


def run_pytest(xml_path: Path, extra: list[str]) -> int:
    """Run pytest, writing JUnit XML. Returns the exit code."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        f"--junitxml={xml_path}",
        "-p",
        "no:logging",
        "-q",
        *extra,
    ]
    print(f"$ {' '.join(command[1:])}\n", file=sys.stderr)
    completed = subprocess.run(command, cwd=BACKEND_ROOT, check=False)
    return completed.returncode


def parse(xml_path: Path) -> Suite:
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()
    # pytest writes <testsuites><testsuite>...; older versions write <testsuite>.
    suites = root.findall("testsuite") or [root]

    result = Suite()
    for suite_node in suites:
        result.duration += float(suite_node.get("time", 0) or 0)
        for node in suite_node.findall("testcase"):
            status = "passed"
            message = ""
            if (failure := node.find("failure")) is not None:
                status = "failed"
                message = (failure.get("message") or "").strip()
            elif (error := node.find("error")) is not None:
                status = "error"
                message = (error.get("message") or "").strip()
            elif (skipped := node.find("skipped")) is not None:
                status = "skipped"
                message = (skipped.get("message") or "").strip()

            result.cases.append(
                Case(
                    name=node.get("name", "?"),
                    classname=node.get("classname", ""),
                    time=float(node.get("time", 0) or 0),
                    status=status,
                    message=message.splitlines()[0][:200] if message else "",
                )
            )
    return result


ICON = {"passed": "PASS", "failed": "FAIL", "error": "ERROR", "skipped": "SKIP"}


def render(suite: Suite, *, quiet: bool) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# QuoteFlow — Automated Testing Report",
        "",
        f"Generated {stamp} by `python scripts/test_report.py`.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total test cases | **{suite.total}** |",
        f"| Passed | **{suite.passed}** |",
        f"| Failed | **{suite.failed}** |",
        f"| Skipped | {suite.skipped} |",
        f"| Pass rate | {suite.pass_rate:.1f}% |",
        f"| Execution time | {suite.duration:.1f} s |",
        "",
    ]

    verdict = (
        "All tests passed."
        if suite.failed == 0
        else f"**{suite.failed} test(s) failed — see the failures section.**"
    )
    lines += [verdict, ""]

    # ---- by area ----------------------------------------------------------
    by_module: dict[str, list[Case]] = {}
    for case in suite.cases:
        by_module.setdefault(case.module, []).append(case)

    lines += [
        "## Results by area",
        "",
        "| Area | Cases | Passed | Failed | Time |",
        "| --- | --- | --- | --- | --- |",
    ]
    for module in sorted(by_module, key=lambda name: AREAS.get(name, "zz") ):
        cases = by_module[module]
        passed = sum(1 for case in cases if case.status == "passed")
        failed = sum(1 for case in cases if case.status in {"failed", "error"})
        elapsed = sum(case.time for case in cases)
        label = AREAS.get(module, module)
        lines.append(
            f"| {label} | {len(cases)} | {passed} | {failed} | {elapsed:.1f} s |"
        )
    lines.append("")

    # ---- failures first, if any ------------------------------------------
    failures = [case for case in suite.cases if case.status in {"failed", "error"}]
    if failures:
        lines += ["## Failures", ""]
        for case in failures:
            where = f"{case.module}" + (f" · {case.group}" if case.group else "")
            lines += [f"### {case.name}", "", f"- Area: {where}"]
            if case.message:
                lines.append(f"- Reason: `{case.message}`")
            lines.append("")

    if quiet:
        return "\n".join(lines).rstrip() + "\n"

    # ---- every case ------------------------------------------------------
    lines += ["## Test case results", ""]
    for module in sorted(by_module, key=lambda name: AREAS.get(name, "zz")):
        cases = by_module[module]
        lines += [f"### {AREAS.get(module, module)}", "", f"`tests/{module}.py`", ""]

        grouped: dict[str, list[Case]] = {}
        for case in cases:
            grouped.setdefault(case.group, []).append(case)

        for group in sorted(grouped):
            if group:
                lines += [f"**{group}**", ""]
            lines += ["| Result | Test | Time |", "| --- | --- | --- |"]
            for case in grouped[group]:
                name = case.name.replace("_", " ")
                lines.append(
                    f"| {ICON[case.status]} | {name} | {case.time:.2f} s |"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the Markdown report here instead of stdout.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Summary and failures only, without the per-case tables.",
    )
    parser.add_argument(
        "--xml",
        type=Path,
        default=BACKEND_ROOT / ".pytest-report.xml",
        help="Where to keep the intermediate JUnit XML.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra arguments passed through to pytest, e.g. -k workflow",
    )
    args = parser.parse_args()

    exit_code = run_pytest(args.xml, args.pytest_args)
    if not args.xml.exists():
        print("pytest produced no report; see its output above.", file=sys.stderr)
        return exit_code or 1

    suite = parse(args.xml)
    report = render(suite, quiet=args.quiet)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(
            f"{suite.passed}/{suite.total} passed in {suite.duration:.1f}s "
            f"-> {args.output}",
            file=sys.stderr,
        )
    else:
        print(report)

    return 0 if suite.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
