"""
Configuration module for the Test Report Processing Pipeline.
Loads settings from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AzureDevOpsConfig:
    """Azure DevOps API configuration."""
    organization: str = ""
    project: str = ""
    pat: str = ""  # Personal Access Token
    base_url: str = ""
    api_version: str = "7.1"

    def __post_init__(self):
        if self.organization and self.project:
            self.base_url = (
                f"https://dev.azure.com/{self.organization}/{self.project}/_apis"
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.organization and self.project and self.pat)


@dataclass
class GeminiConfig:
    """Google Gemini AI configuration."""
    api_key: str = ""
    model: str = "gemini-2.0-flash"
    max_tokens: int = 4096
    temperature: float = 0.3

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class PipelineConfig:
    """Main pipeline configuration."""
    # Paths
    report_input_dir: str = ""
    report_output_dir: str = ""
    bug_output_dir: str = ""

    # Report framework: "mochawesome", "playwright", "pytest"
    framework: str = "mochawesome"

    # Azure DevOps
    azure: AzureDevOpsConfig = field(default_factory=AzureDevOpsConfig)

    # Gemini AI
    gemini: GeminiConfig = field(default_factory=GeminiConfig)

    # Bug ticket target: "azure", "jira", "file"
    bug_target: str = "file"

    # JIRA (optional)
    jira_url: str = ""
    jira_email: str = ""
    jira_token: str = ""
    jira_project_key: str = ""

    # Bug template path (optional, for custom templates from manual team)
    bug_template_path: str = ""

    # Environment label for reports
    environment: str = "QA"
    project_name: str = "Unified-Test-Automation"


def load_config(env_file: Optional[str] = None) -> PipelineConfig:
    """
    Load pipeline configuration from environment variables.
    Optionally loads from a .env file first.
    """
    if env_file:
        _load_dotenv(env_file)

    base_dir = Path(__file__).parent

    azure = AzureDevOpsConfig(
        organization=os.getenv("AZURE_DEVOPS_ORG", ""),
        project=os.getenv("AZURE_DEVOPS_PROJECT", ""),
        pat=os.getenv("AZURE_DEVOPS_PAT", ""),
    )

    gemini = GeminiConfig(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    )

    return PipelineConfig(
        report_input_dir=os.getenv(
            "REPORT_INPUT_DIR",
            str(base_dir / "input"),
        ),
        report_output_dir=os.getenv(
            "REPORT_OUTPUT_DIR",
            str(base_dir / "output" / "reports"),
        ),
        bug_output_dir=os.getenv(
            "BUG_OUTPUT_DIR",
            str(base_dir / "output" / "bugs"),
        ),
        framework=os.getenv("REPORT_FRAMEWORK", "mochawesome"),
        azure=azure,
        gemini=gemini,
        bug_target=os.getenv("BUG_TARGET", "file"),
        jira_url=os.getenv("JIRA_URL", ""),
        jira_email=os.getenv("JIRA_EMAIL", ""),
        jira_token=os.getenv("JIRA_TOKEN", ""),
        jira_project_key=os.getenv("JIRA_PROJECT_KEY", ""),
        bug_template_path=os.getenv("BUG_TEMPLATE_PATH", ""),
        environment=os.getenv("TEST_ENVIRONMENT", "QA"),
        project_name=os.getenv("PROJECT_NAME", "Unified-Test-Automation"),
    )


def _load_dotenv(filepath: str) -> None:
    """Simple .env file loader (no external dependency needed)."""
    path = Path(filepath)
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            os.environ.setdefault(key, value)
