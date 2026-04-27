"""
Failure extractor — identifies failed tests and enriches them with metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from parsers.base_parser import TestReport, TestResult


@dataclass
class FailureDetail:
    """Enriched failure information for a single test."""
    test: TestResult

    # Extracted / classified info
    failure_category: str = ""  # e.g. "Network Error", "Assertion Failure", "Timeout"
    affected_component: str = ""
    suggested_priority: str = "Medium"  # "Critical", "High", "Medium", "Low"

    # From Azure DevOps (populated later)
    ado_test_case_id: str = ""
    ado_test_case_title: str = ""
    ado_repro_steps: str = ""
    ado_area_path: str = ""

    # AI-enhanced (populated later)
    ai_summary: str = ""
    ai_root_cause: str = ""
    ai_bug_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.test.to_dict(),
            "failure_category": self.failure_category,
            "affected_component": self.affected_component,
            "suggested_priority": self.suggested_priority,
            "ado_test_case_id": self.ado_test_case_id,
            "ado_test_case_title": self.ado_test_case_title,
            "ado_repro_steps": self.ado_repro_steps,
            "ai_summary": self.ai_summary,
            "ai_root_cause": self.ai_root_cause,
            "ai_bug_description": self.ai_bug_description,
        }


class FailureExtractor:
    """Extracts and classifies failures from a parsed test report."""

    # Error classification patterns
    CATEGORY_PATTERNS: list[tuple[str, str, str]] = [
        # (regex_pattern, category, default_priority)
        (r"AxiosError.*Network Error", "Network Error", "High"),
        (r"TimeoutError|Timed out|timeout", "Timeout", "High"),
        (r"AssertionError|Expected.*but", "Assertion Failure", "Medium"),
        (r"TypeError|ReferenceError|SyntaxError", "Code Error", "High"),
        (r"ECONNREFUSED|ENOTFOUND|ECONNRESET", "Connection Error", "Critical"),
        (r"401|403|Unauthorized|Forbidden", "Auth Failure", "High"),
        (r"404|Not Found", "Resource Not Found", "Medium"),
        (r"500|Internal Server Error", "Server Error", "Critical"),
        (r"Element.*not found|never found it", "Element Not Found", "Medium"),
        (r"detached from the DOM", "Stale Element", "Medium"),
        (r"navigation|page crash", "Navigation Error", "High"),
    ]

    def extract(self, report: TestReport) -> list[FailureDetail]:
        """Extract all failures from a report with classification."""
        failures = []
        for test in report.failed_tests:
            detail = FailureDetail(test=test)
            self._classify(detail)
            self._extract_component(detail)
            failures.append(detail)
        return failures

    def _classify(self, detail: FailureDetail) -> None:
        """Classify the failure based on error message patterns."""
        text = f"{detail.test.error_message} {detail.test.error_stack}"
        for pattern, category, priority in self.CATEGORY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detail.failure_category = category
                detail.suggested_priority = priority
                return
        detail.failure_category = "Unknown"
        detail.suggested_priority = "Medium"

    def _extract_component(self, detail: FailureDetail) -> None:
        """Extract the affected component/module from the error stack or file path."""
        # Try from the file path
        file_path = detail.test.file_path
        if file_path:
            # e.g. cypress/scenarios/UserJourney/1-e2e-ecotools-journey.cy.ts
            parts = file_path.replace("\\", "/").split("/")
            # Find the scenario category
            for i, part in enumerate(parts):
                if part in ("scenarios", "tests", "specs"):
                    if i + 1 < len(parts):
                        detail.affected_component = parts[i + 1]
                        return

        # Try from the suite name
        if detail.test.suite_name:
            detail.affected_component = detail.test.suite_name

        # Try from the error stack — extract the function/page name
        stack = detail.test.error_stack
        if stack:
            match = re.search(
                r"at (\w+(?:\.\w+)?)\s*\(", stack
            )
            if match:
                detail.affected_component = match.group(1)
