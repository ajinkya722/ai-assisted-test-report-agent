"""
Base parser and shared data models for test report parsing.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TestResult:
    """Normalized test result from any framework."""
    uuid: str
    title: str
    full_title: str
    state: str  # "passed", "failed", "pending", "skipped"
    duration_ms: int
    suite_name: str
    file_path: str

    # Failure details
    error_message: str = ""
    error_stack: str = ""

    # Optional metadata
    test_id: str = ""  # Azure DevOps / framework test case ID
    tags: list[str] = field(default_factory=list)
    retry_count: int = 0
    context: Optional[str] = None
    code_snippet: str = ""

    @property
    def is_failed(self) -> bool:
        return self.state == "failed"

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000.0

    @property
    def duration_display(self) -> str:
        secs = self.duration_seconds
        if secs >= 60:
            mins = int(secs // 60)
            remaining = secs % 60
            return f"{mins}m {remaining:.1f}s"
        return f"{secs:.1f}s"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "title": self.title,
            "full_title": self.full_title,
            "state": self.state,
            "duration_ms": self.duration_ms,
            "duration_display": self.duration_display,
            "suite_name": self.suite_name,
            "file_path": self.file_path,
            "error_message": self.error_message,
            "error_stack": self.error_stack,
            "test_id": self.test_id,
            "tags": self.tags,
        }


@dataclass
class TestSuite:
    """Normalized test suite."""
    name: str
    file_path: str
    tests: list[TestResult] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.state == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.state == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.state in ("pending", "skipped"))


@dataclass
class TestReport:
    """Aggregated report from one or more test suite files."""
    framework: str
    suites: list[TestSuite] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    total_duration_ms: int = 0
    environment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_tests(self) -> list[TestResult]:
        return [t for suite in self.suites for t in suite.tests]

    @property
    def failed_tests(self) -> list[TestResult]:
        return [t for t in self.all_tests if t.is_failed]

    @property
    def passed_tests(self) -> list[TestResult]:
        return [t for t in self.all_tests if t.state == "passed"]

    @property
    def total(self) -> int:
        return len(self.all_tests)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (len(self.passed_tests) / self.total) * 100

    def summary(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "total_tests": self.total,
            "passed": len(self.passed_tests),
            "failed": len(self.failed_tests),
            "skipped": sum(
                1 for t in self.all_tests if t.state in ("pending", "skipped")
            ),
            "pass_rate": round(self.pass_rate, 2),
            "total_duration_ms": self.total_duration_ms,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class BaseParser(ABC):
    """Abstract base for all report parsers."""

    @abstractmethod
    def parse_file(self, filepath: str | Path) -> TestReport:
        """Parse a single report file."""

    @abstractmethod
    def parse_directory(self, dirpath: str | Path) -> TestReport:
        """Parse all report files in a directory."""

    @staticmethod
    def _load_json(filepath: str | Path) -> dict:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _extract_test_id(title: str) -> str:
        """
        Extract test ID from title if it follows patterns like:
        - '[TC-1234] Test title'
        - 'TC_1234: Test title'
        - 'EcoTools-E2E-Journey 7: ...'
        """
        import re
        # Pattern: [TC-1234] or [TCID-1234]
        match = re.search(r"\[([A-Z]{2,}-\d+)\]", title)
        if match:
            return match.group(1)
        # Pattern: Journey N: or Test N:
        match = re.search(r"(?:Journey|Test|TC)\s*(\d+)\s*:", title)
        if match:
            return match.group(1)
        return ""
