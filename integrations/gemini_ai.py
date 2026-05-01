"""
Gemini AI integration — generate enhanced failure summaries and bug descriptions.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import ssl
from typing import Any, Optional

from config import GeminiConfig
from extractors.failure_extractor import FailureDetail

logger = logging.getLogger(__name__)


class GeminiAIClient:
    """Client for Google Gemini API to enhance failure analysis."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: GeminiConfig):
        self.config = config

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API and return the text response."""
        if not self.config.is_configured:
            return ""

        url = (
            f"{self.API_BASE}/{self.config.model}:generateContent"
            f"?key={self.config.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            },
        }

        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""

    def enhance_failure(
        self,
        failure: FailureDetail,
        bug_template: str = "",
    ) -> None:
        """Use AI to generate summary, root cause, and bug description for a failure."""
        if not self.config.is_configured:
            logger.info("Gemini not configured — skipping AI enhancement")
            return

        try:
            # Generate failure summary + root cause
            analysis = self._analyze_failure(failure)
            if analysis:
                failure.ai_summary = analysis.get("summary", "")
                failure.ai_root_cause = analysis.get("root_cause", "")

            # Generate structured bug description
            bug_desc = self._generate_bug_description(failure, bug_template)
            if bug_desc:
                failure.ai_bug_description = bug_desc

        except Exception as e:
            logger.warning(f"AI enhancement failed for '{failure.test.title}': {e}")

    def _analyze_failure(self, failure: FailureDetail) -> dict[str, str]:
        """Analyze a test failure and return summary + root cause analysis."""
        prompt = f"""You are a senior QA engineer analyzing automated test failures.

Analyze the following test failure and provide:
1. A concise **summary** (2-3 sentences) explaining what failed and why
2. A **root_cause** analysis (2-3 sentences) suggesting the most likely cause

Test Details:
- Test Name: {failure.test.full_title}
- Suite: {failure.test.suite_name}
- File: {failure.test.file_path}
- Duration: {failure.test.duration_display}
- Category: {failure.failure_category}

Error Message:
{failure.test.error_message}

Error Stack:
{failure.test.error_stack[:2000]}

{f"Reproduction Steps (from test case):{chr(10)}{failure.ado_repro_steps[:1000]}" if failure.ado_repro_steps else ""}

Respond ONLY in this exact JSON format (no markdown, no code blocks):
{{"summary": "...", "root_cause": "..."}}"""

        response = self._call_gemini(prompt)
        try:
            # Handle potential markdown code block wrapping
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {"summary": response.strip(), "root_cause": ""}

    def _generate_bug_description(
        self, failure: FailureDetail, template: str = ""
    ) -> str:
        """Generate a structured bug report description."""
        template_instruction = ""
        if template:
            template_instruction = f"""
Use the following bug report template structure:
{template}
"""

        default_template = """
## Bug Title
[Auto-generated title]

## Environment
- Framework: Cypress / Mochawesome
- Test File: [file path]
- Test Suite: [suite name]

## Description
[Clear description of what happened]

## Steps to Reproduce
1. [Steps from the test]

## Expected Result
[What should have happened]

## Actual Result
[What actually happened, including error message]

## Error Details
```
[Error stack trace]
```

## Severity / Priority
[Suggested priority]

## Root Cause Analysis
[AI analysis of probable root cause]

## Additional Context
- Test Duration: [duration]
- Failure Category: [category]
- Test ID: [ID if available]
"""

        prompt = f"""You are a senior QA engineer writing a bug report for a failed automated test.

Generate a well-structured bug report based on the following failure details.
{template_instruction if template_instruction else f"Use this template structure:{default_template}"}

Test Failure Details:
- Test: {failure.test.full_title}
- Suite: {failure.test.suite_name}
- File: {failure.test.file_path}
- Duration: {failure.test.duration_display}
- Category: {failure.failure_category}
- Priority: {failure.suggested_priority}

Error Message:
{failure.test.error_message}

Error Stack (first 1500 chars):
{failure.test.error_stack[:1500]}

{f"AI Summary: {failure.ai_summary}" if failure.ai_summary else ""}
{f"AI Root Cause: {failure.ai_root_cause}" if failure.ai_root_cause else ""}
{f"Reproduction Steps from ADO:{chr(10)}{failure.ado_repro_steps[:1000]}" if failure.ado_repro_steps else ""}

Generate a complete, professional bug report in Markdown format. Be specific and actionable."""

        return self._call_gemini(prompt)

    def generate_executive_summary(
        self,
        total: int,
        passed: int,
        failed: int,
        skipped: int,
        failures: list[FailureDetail],
        environment: str = "QA",
    ) -> str:
        """Generate an executive summary of the test run."""
        if not self.config.is_configured:
            return ""

        failure_bullets = "\n".join(
            f"- {f.test.title}: {f.failure_category} — {f.test.error_message[:100]}"
            for f in failures[:10]
        )

        prompt = f"""You are a QA lead writing a brief executive summary of a test execution report.

Test execution results for {environment} environment:
- Total tests: {total}
- Passed: {passed}
- Failed: {failed}
- Skipped: {skipped}
- Pass rate: {(passed/total*100) if total else 0:.1f}%

Failed tests:
{failure_bullets}

Write a concise (4-6 sentences) executive summary covering:
1. Overall health assessment
2. Key failure patterns
3. Risk areas
4. Recommendation for next steps

Keep it professional and actionable. Plain text, no markdown headers."""

        try:
            return self._call_gemini(prompt)
        except Exception as e:
            logger.warning(f"Failed to generate executive summary: {e}")
            return ""
