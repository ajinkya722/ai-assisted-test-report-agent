"""
Bug ticket generator — creates pre-formatted bug tickets as files,
or pushes them directly to Azure DevOps / JIRA.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import PipelineConfig
from extractors.failure_extractor import FailureDetail
from integrations.azure_devops import AzureDevOpsClient

logger = logging.getLogger(__name__)


class BugTicketGenerator:
    """Generates bug tickets from failure details."""

    def __init__(self, config: PipelineConfig, ado_client: Optional[AzureDevOpsClient] = None):
        self.config = config
        self.ado_client = ado_client
        self._bug_template = self._load_template()

    def _load_template(self) -> str:
        """Load custom bug template if provided."""
        if self.config.bug_template_path:
            path = Path(self.config.bug_template_path)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    def generate_all(
        self, failures: list[FailureDetail]
    ) -> list[dict[str, Any]]:
        """Generate bug tickets for all failures. Returns list of ticket info dicts."""
        results = []
        for failure in failures:
            result = self.generate_ticket(failure)
            if result:
                results.append(result)
        return results

    def generate_ticket(self, failure: FailureDetail) -> Optional[dict[str, Any]]:
        """Generate a single bug ticket. Returns ticket info or None."""
        target = self.config.bug_target.lower()

        if target == "azure":
            return self._create_azure_bug(failure)
        elif target == "jira":
            return self._create_jira_bug(failure)
        else:
            return self._create_file_bug(failure)

    # ── File-based tickets ────────────────────────────────────────────────

    def _create_file_bug(self, failure: FailureDetail) -> dict[str, Any]:
        """Write bug ticket to a markdown file."""
        os.makedirs(self.config.bug_output_dir, exist_ok=True)

        # Sanitize filename
        safe_title = re.sub(r'[^\w\s-]', '', failure.test.title)[:80].strip()
        safe_title = re.sub(r'\s+', '-', safe_title)
        filename = f"BUG-{safe_title}.md"
        filepath = os.path.join(self.config.bug_output_dir, filename)

        content = self._format_bug_markdown(failure)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Bug ticket written to: {filepath}")
        repro = failure.ado_repro_steps or self._generate_repro_steps(failure)
        return {
            "type": "file",
            "path": filepath,
            "title": self._bug_title(failure),
            "priority": failure.suggested_priority,
            "category": failure.failure_category,
            "component": failure.affected_component,
            "error_message": failure.test.error_message,
            "test_file": failure.test.file_path,
            "duration": failure.test.duration_display,
            "steps_to_reproduce": repro,
        }

    def _format_bug_markdown(self, failure: FailureDetail) -> str:
        """Format bug ticket as markdown."""
        # Use AI-generated description if available
        if failure.ai_bug_description:
            return failure.ai_bug_description

        title = self._bug_title(failure)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        repro_steps = failure.ado_repro_steps or self._generate_repro_steps(failure)

        return f"""# {title}

**Date:** {timestamp}
**Priority:** {failure.suggested_priority}
**Severity:** {failure.failure_category}
**Environment:** {self.config.environment}
**Project:** {self.config.project_name}

---

## Description

Automated test **"{failure.test.title}"** in suite **"{failure.test.suite_name}"** failed during execution.

**Test File:** `{failure.test.file_path}`
**Duration:** {failure.test.duration_display}
**Component:** {failure.affected_component}
{f"**Test Case ID:** {failure.ado_test_case_id}" if failure.ado_test_case_id else ""}

---

## Error Message

```
{failure.test.error_message}
```

## Steps to Reproduce

{repro_steps}

## Expected Result

The test "{failure.test.title}" should pass without errors.

## Actual Result

The test failed with a **{failure.failure_category}** error:
```
{failure.test.error_message}
```

## Stack Trace

```
{failure.test.error_stack[:2000]}
```

{f'''## AI Analysis

**Summary:** {failure.ai_summary}

**Root Cause:** {failure.ai_root_cause}
''' if failure.ai_summary else ""}

---

## Additional Information

- **Framework:** Cypress / Mochawesome
- **Suite:** {failure.test.suite_name}
- **Tags:** {', '.join(failure.test.tags) if failure.test.tags else 'N/A'}
{f"- **ADO Test Case:** #{failure.ado_test_case_id} — {failure.ado_test_case_title}" if failure.ado_test_case_id else ""}

---
*Auto-generated by Test Report Pipeline*
"""

    # ── Azure DevOps tickets ──────────────────────────────────────────────

    def _create_azure_bug(self, failure: FailureDetail) -> Optional[dict[str, Any]]:
        """Create a bug in Azure DevOps."""
        if not self.ado_client or not self.config.azure.is_configured:
            logger.warning("Azure DevOps not configured — falling back to file")
            return self._create_file_bug(failure)

        title = self._bug_title(failure)

        # HTML description for Azure DevOps
        description = self._format_bug_html(failure)
        repro_steps = self._format_repro_html(failure)

        priority = AzureDevOpsClient.priority_to_int(failure.suggested_priority)
        severity = AzureDevOpsClient.priority_to_severity(failure.suggested_priority)

        result = self.ado_client.create_bug(
            title=title,
            description=description,
            repro_steps=repro_steps,
            priority=priority,
            severity=severity,
            area_path=failure.ado_area_path,
            tags="AutoGenerated;TestFailure;" + failure.failure_category,
        )

        if result:
            # Also write a local copy
            self._create_file_bug(failure)
            repro = failure.ado_repro_steps or self._generate_repro_steps(failure)
            return {
                "type": "azure",
                "id": result.get("id"),
                "url": result.get("url", ""),
                "title": title,
                "priority": failure.suggested_priority,
                "category": failure.failure_category,
                "component": failure.affected_component,
                "error_message": failure.test.error_message,
                "test_file": failure.test.file_path,
                "duration": failure.test.duration_display,
                "steps_to_reproduce": repro,
            }
        return self._create_file_bug(failure)

    def _format_bug_html(self, failure: FailureDetail) -> str:
        """Format bug description as HTML for Azure DevOps."""
        import html
        ai_section = ""
        if failure.ai_summary:
            ai_section = f"""
<h3>AI Analysis</h3>
<p><strong>Summary:</strong> {html.escape(failure.ai_summary)}</p>
<p><strong>Root Cause:</strong> {html.escape(failure.ai_root_cause)}</p>"""

        return f"""<h3>Description</h3>
<p>Automated test <strong>{html.escape(failure.test.title)}</strong>
in suite <strong>{html.escape(failure.test.suite_name)}</strong> failed.</p>

<p><strong>File:</strong> {html.escape(failure.test.file_path)}<br/>
<strong>Duration:</strong> {failure.test.duration_display}<br/>
<strong>Category:</strong> {html.escape(failure.failure_category)}<br/>
<strong>Component:</strong> {html.escape(failure.affected_component)}</p>

<h3>Error</h3>
<pre>{html.escape(failure.test.error_message)}</pre>

<h3>Stack Trace</h3>
<pre>{html.escape(failure.test.error_stack[:2000])}</pre>
{ai_section}"""

    def _format_repro_html(self, failure: FailureDetail) -> str:
        """Format repro steps as HTML for Azure DevOps."""
        import html
        if failure.ado_repro_steps:
            return failure.ado_repro_steps  # Already HTML from ADO

        steps = self._generate_repro_steps(failure)
        return f"<pre>{html.escape(steps)}</pre>"

    # ── JIRA tickets (placeholder) ────────────────────────────────────────

    def _create_jira_bug(self, failure: FailureDetail) -> Optional[dict[str, Any]]:
        """
        Create a bug in JIRA. This is a placeholder — implement JIRA REST API
        calls using self.config.jira_* settings when ready.
        """
        if not self.config.jira_url or not self.config.jira_token:
            logger.warning("JIRA not configured — falling back to file")
            return self._create_file_bug(failure)

        # JIRA REST API v3 integration placeholder
        # Implement using:
        #   POST {jira_url}/rest/api/3/issue
        #   Auth: Basic (email:token base64)
        #   Body: { "fields": { "project": {"key": jira_project_key}, "summary": ..., "issuetype": {"name": "Bug"}, ... }}
        logger.info("JIRA integration: generating file-based ticket (implement API calls for auto-creation)")
        return self._create_file_bug(failure)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _bug_title(failure: FailureDetail) -> str:
        """Generate a concise bug title."""
        prefix = f"[{failure.failure_category}]"
        test_name = failure.test.title
        # Truncate if too long
        max_len = 150
        if len(f"{prefix} {test_name}") > max_len:
            test_name = test_name[: max_len - len(prefix) - 4] + "..."
        return f"{prefix} {test_name}"

    @staticmethod
    def _generate_repro_steps(failure: FailureDetail) -> str:
        """Generate detailed repro steps by parsing the actual test code."""
        code = failure.test.code_snippet
        if code:
            steps = BugTicketGenerator._parse_code_to_steps(code, failure)
            if steps:
                return steps

        # Fallback: derive steps from error stack location
        stack_step = ""
        if failure.test.error_stack:
            import re
            match = re.search(r"at (\w+(?:\.\w+)?)\s*\(", failure.test.error_stack)
            if match:
                stack_step = f"\n5. Failure occurs at: {match.group(1)}()"

        return (
            f"1. Login to the application ({failure.test.suite_name})\n"
            f"2. Navigate to the module: {failure.affected_component or 'N/A'}\n"
            f"3. Execute scenario: {failure.test.title}\n"
            f"4. Observe the error: {failure.test.error_message[:200]}"
            f"{stack_step}"
        )

    @staticmethod
    def _parse_code_to_steps(code: str, failure: FailureDetail) -> str:
        """Parse Cypress/test code into human-readable numbered repro steps."""
        import re

        # Map common page-object method calls to human-readable actions
        METHOD_MAP = [
            (r"checkAndLoginRIBHub\(([^)]+)\)", "Login to RIB HUB as {0}"),
            (r"selectTenantfromControlCenter", "Open Control Center and select Tenant"),
            (r"selectCompaniesfromControlCenter", "Open Control Center and select Companies"),
            (r"selectUsersfromControlCenter", "Open Control Center and select Users"),
            (r"selectProjectsfromControlCenter", "Open Control Center and select Projects"),
            (r"enterInput\([^,]+,\s*([^)]+)\)", "Enter input value: {0}"),
            (r"hoverAndClickQuickView", "Hover on row and click Quick View"),
            (r"hoverAndClickGoTo", "Hover on row and click Go To"),
            (r"selectCompanyTab\([^'\"]*['\"]([^'\"]+)['\"]", "Select the '{0}' tab"),
            (r"selectCompanyTab\([^)]+\.([a-zA-Z]+)\)", "Select the '{0}' tab"),
            (r"createNewCompany", "Create a new Company with provided details"),
            (r"createNewTenant", "Create a new Tenant with provided details"),
            (r"createNewProject", "Create a new Project with provided details"),
            (r"createNewPermission", "Create a new Permission/Role"),
            (r"createNewTeamFromProjects", "Create a new Team from Projects"),
            (r"createCompanyTeamWithAllFields", "Create a new Company Team"),
            (r"inviteCompanyOrProjectUser\(([^,]+),\s*([^)]+)\)", "Invite user {0} with role {1}"),
            (r"inviteUser(?:NewIA)?\(([^,]+)", "Invite user: {0}"),
            (r"revokeInvitedUser", "Revoke the invited user"),
            (r"resendRequest", "Resend the invitation"),
            (r"fetchInvitationLinks", "Fetch invitation links via API"),
            (r"createProfile", "Complete user registration / create profile"),
            (r"editUserDetails", "Edit user details (name, contact, address)"),
            (r"editCompanyGeneralInfo", "Edit company general information"),
            (r"editTenantGeneralInfo", "Edit tenant general information"),
            (r"editGeneralInfo", "Edit general information"),
            (r"editTeamDetails", "Edit team details"),
            (r"editProjectViaGoTo", "Edit project details via Go To"),
            (r"verifyUserStatusInGrid\([^)]*status(\w+)", "Verify user status is '{0}' in grid"),
            (r"verifyRecordInTable\([^,]+,\s*([^)]+)\)", "Verify record '{0}' appears in table"),
            (r"verifyCompanyDetails", "Verify company details"),
            (r"verifyActiveTenantDetails", "Verify active tenant details"),
            (r"verifyUpdatedTenantDetails", "Verify updated tenant details"),
            (r"verifyCompanyPermissionsExist", "Verify company permissions exist"),
            (r"verifyUserDetails", "Verify user details in drawer"),
            (r"assignPermission(?:ToUser|FromUsers)\(([^)]+)\)", "Assign permission to user: {0}"),
            (r"addCompanyUser", "Add company user to project"),
            (r"archiveProject", "Archive the project"),
            (r"activeArchivedProject", "Re-activate the archived project"),
            (r"inactivateCompany", "Inactivate the company"),
            (r"activateCompany", "Activate the company"),
            (r"inactivateTenant", "Inactivate the tenant"),
            (r"activateTenant", "Activate the tenant"),
            (r"duplicateProject\(([^,]+),\s*([^)]+)\)", "Duplicate project with code {0}, name {1}"),
            (r"markProjectAsStar", "Mark project as starred"),
            (r"unmarkProjectAsStarred", "Unmark project as starred"),
            (r"goBack\(\)", "Navigate back"),
            (r"logOut\(\)", "Logout from application"),
            (r"hardRefresh\(\)", "Hard refresh the page"),
            (r"closeModal", "Close the modal/drawer"),
            (r"clickOnButton(?:Text)?\(([^)]+)\)", "Click button: {0}"),
            (r"writeRequest", None),  # Skip internal data writes
            (r"cy\.session", None),   # Skip session setup internals
            (r"cy\.wait", None),       # Skip waits
            (r"cy\.log", None),        # Skip logs
            (r"cy\.readFile", None),   # Skip file reads
            (r"cy\.writeFile", None),  # Skip file writes
            (r"console\.log", None),   # Skip console logs
        ]

        lines = code.split("\n")
        steps: list[str] = []
        seen: set[str] = set()

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("//"):
                continue

            for pattern, template in METHOD_MAP:
                match = re.search(pattern, line_stripped)
                if match:
                    if template is None:
                        break  # Skip this line entirely
                    # Fill placeholders with captured groups
                    step = template
                    for i, group in enumerate(match.groups()):
                        clean_val = group.strip().strip("'\"").strip()
                        # Shorten variable references
                        if "." in clean_val and not " " in clean_val:
                            clean_val = clean_val.split(".")[-1]
                        step = step.replace(f"{{{i}}}", clean_val)
                    # Deduplicate identical steps
                    if step not in seen:
                        seen.add(step)
                        steps.append(step)
                    break

        if not steps:
            return ""

        # Add the failure step at the end
        steps.append(
            f"**FAILURE:** {failure.test.error_message[:200]}"
        )

        return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))

    def generate_summary_json(
        self, tickets: list[dict[str, Any]], output_path: str
    ) -> str:
        """Write a JSON summary of all generated tickets."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_bugs": len(tickets),
                    "tickets": tickets,
                },
                f,
                indent=2,
            )
        return output_path
