"""
Azure DevOps integration — fetch test case details and create/update work items.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.parse
import urllib.request
import ssl
from typing import Any, Optional

from config import AzureDevOpsConfig
from extractors.failure_extractor import FailureDetail

logger = logging.getLogger(__name__)


class AzureDevOpsClient:
    """Client for Azure DevOps REST API interactions."""

    def __init__(self, config: AzureDevOpsConfig):
        self.config = config
        self._auth_header = self._build_auth_header()

    def _build_auth_header(self) -> str:
        token = base64.b64encode(f":{self.config.pat}".encode()).decode()
        return f"Basic {token}"

    def _request(
        self,
        method: str,
        url: str,
        data: Optional[dict | list] = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to Azure DevOps API."""
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": content_type,
        }
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        # Allow HTTPS connections
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── Test Case Operations ──────────────────────────────────────────────

    def get_test_case(self, test_case_id: str) -> Optional[dict[str, Any]]:
        """Fetch a test case work item by ID."""
        if not self.config.is_configured or not test_case_id:
            return None

        try:
            url = (
                f"{self.config.base_url}/wit/workitems/{test_case_id}"
                f"?$expand=all&api-version={self.config.api_version}"
            )
            result = self._request("GET", url)
            return self._extract_test_case_fields(result)
        except Exception as e:
            logger.warning(f"Failed to fetch test case {test_case_id}: {e}")
            return None

    def search_test_cases(self, query: str) -> list[dict[str, Any]]:
        """Search for test cases by title using WIQL."""
        if not self.config.is_configured:
            return []

        try:
            wiql_url = (
                f"{self.config.base_url}/wit/wiql"
                f"?api-version={self.config.api_version}"
            )
            # Sanitize query to prevent WIQL injection
            safe_query = query.replace("'", "''")
            wiql = {
                "query": (
                    "SELECT [System.Id], [System.Title] "
                    "FROM WorkItems "
                    "WHERE [System.WorkItemType] = 'Test Case' "
                    f"AND [System.Title] CONTAINS '{safe_query}' "
                    "ORDER BY [System.CreatedDate] DESC"
                )
            }
            result = self._request("POST", wiql_url, wiql)
            work_items = result.get("workItems", [])
            return [{"id": wi["id"], "url": wi.get("url", "")} for wi in work_items[:10]]
        except Exception as e:
            logger.warning(f"Failed to search test cases: {e}")
            return []

    def enrich_failure_with_test_case(self, failure: FailureDetail) -> None:
        """Enrich a failure detail with Azure DevOps test case information."""
        test_id = failure.test.test_id or failure.ado_test_case_id
        if not test_id:
            # Try to search by title
            results = self.search_test_cases(failure.test.title)
            if results:
                test_id = str(results[0]["id"])

        if not test_id:
            return

        tc = self.get_test_case(test_id)
        if tc:
            failure.ado_test_case_id = str(tc.get("id", ""))
            failure.ado_test_case_title = tc.get("title", "")
            failure.ado_repro_steps = tc.get("repro_steps", "")
            failure.ado_area_path = tc.get("area_path", "")

    # ── Bug Work Item Operations ──────────────────────────────────────────

    def create_bug(
        self,
        title: str,
        description: str,
        repro_steps: str,
        priority: int = 2,
        severity: str = "2 - High",
        area_path: str = "",
        tags: str = "",
        assigned_to: str = "",
    ) -> Optional[dict[str, Any]]:
        """Create a Bug work item in Azure DevOps."""
        if not self.config.is_configured:
            logger.warning("Azure DevOps not configured — skipping bug creation")
            return None

        try:
            url = (
                f"{self.config.base_url}/wit/workitems/$Bug"
                f"?api-version={self.config.api_version}"
            )
            patch_doc = [
                {"op": "add", "path": "/fields/System.Title", "value": title},
                {
                    "op": "add",
                    "path": "/fields/System.Description",
                    "value": description,
                },
                {
                    "op": "add",
                    "path": "/fields/Microsoft.VSTS.TCM.ReproSteps",
                    "value": repro_steps,
                },
                {
                    "op": "add",
                    "path": "/fields/Microsoft.VSTS.Common.Priority",
                    "value": priority,
                },
                {
                    "op": "add",
                    "path": "/fields/Microsoft.VSTS.Common.Severity",
                    "value": severity,
                },
            ]
            if area_path:
                patch_doc.append(
                    {"op": "add", "path": "/fields/System.AreaPath", "value": area_path}
                )
            if tags:
                patch_doc.append(
                    {"op": "add", "path": "/fields/System.Tags", "value": tags}
                )
            if assigned_to:
                patch_doc.append(
                    {
                        "op": "add",
                        "path": "/fields/System.AssignedTo",
                        "value": assigned_to,
                    }
                )

            result = self._request(
                "POST",
                url,
                data=patch_doc,
                content_type="application/json-patch+json",
            )
            bug_id = result.get("id")
            logger.info(f"Created Azure DevOps bug #{bug_id}: {title}")
            return {"id": bug_id, "url": result.get("_links", {}).get("html", {}).get("href", "")}
        except Exception as e:
            logger.error(f"Failed to create bug: {e}")
            return None

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_test_case_fields(work_item: dict) -> dict[str, Any]:
        fields = work_item.get("fields", {})
        return {
            "id": work_item.get("id"),
            "title": fields.get("System.Title", ""),
            "state": fields.get("System.State", ""),
            "area_path": fields.get("System.AreaPath", ""),
            "repro_steps": fields.get("Microsoft.VSTS.TCM.ReproSteps", ""),
            "description": fields.get("System.Description", ""),
            "steps": fields.get("Microsoft.VSTS.TCM.Steps", ""),
            "assigned_to": fields.get("System.AssignedTo", {}).get(
                "displayName", ""
            )
            if isinstance(fields.get("System.AssignedTo"), dict)
            else fields.get("System.AssignedTo", ""),
            "tags": fields.get("System.Tags", ""),
        }

    @staticmethod
    def priority_to_int(priority_str: str) -> int:
        """Convert priority string to Azure DevOps numeric priority."""
        mapping = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}
        return mapping.get(priority_str, 3)

    @staticmethod
    def priority_to_severity(priority_str: str) -> str:
        mapping = {
            "Critical": "1 - Critical",
            "High": "2 - High",
            "Medium": "3 - Medium",
            "Low": "4 - Low",
        }
        return mapping.get(priority_str, "3 - Medium")
