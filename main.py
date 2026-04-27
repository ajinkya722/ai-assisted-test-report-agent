"""
Main pipeline orchestrator — wires together all modules to process
test reports end-to-end.

Usage:
    python main.py                          # Uses defaults (reads from ./input)
    python main.py --input path/to/reports  # Custom input directory
    python main.py --html-only              # Skip AI and ADO enrichment
    python main.py --env-file .env          # Load config from .env file
    python main.py --input report.html --parse-html  # Parse Mochawesome HTML directly
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure report-pipeline dir is on the path
sys.path.insert(0, str(Path(__file__).parent))

from config import PipelineConfig, load_config
from parsers import MochawesomeParser, PlaywrightParser, PytestParser, BaseParser
from parsers.base_parser import TestReport
from extractors.failure_extractor import FailureExtractor, FailureDetail
from integrations.azure_devops import AzureDevOpsClient
from integrations.gemini_ai import GeminiAIClient
from generators.html_report import HTMLReportGenerator
from generators.bug_ticket import BugTicketGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def get_parser(framework: str) -> BaseParser:
    """Return the correct parser for the given framework."""
    parsers = {
        "mochawesome": MochawesomeParser,
        "cypress": MochawesomeParser,
        "playwright": PlaywrightParser,
        "pytest": PytestParser,
        "selenium": PytestParser,
    }
    cls = parsers.get(framework.lower())
    if not cls:
        raise ValueError(
            f"Unsupported framework: {framework}. "
            f"Supported: {', '.join(parsers.keys())}"
        )
    return cls()


def run_pipeline(config: PipelineConfig, input_path: str = "", parse_html: bool = False) -> dict:
    """
    Execute the full pipeline:
    1. Parse reports
    2. Extract failures
    3. Enrich with Azure DevOps test case data
    4. Enhance with Gemini AI
    5. Generate HTML report
    6. Generate bug tickets
    """
    input_dir = input_path or config.report_input_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Step 1: Parse Reports ─────────────────────────────────────────────
    logger.info(f"Step 1/6: Parsing {config.framework} reports from: {input_dir}")
    parser = get_parser(config.framework)

    input_path_obj = Path(input_dir)
    if parse_html and input_path_obj.is_file() and input_path_obj.suffix == ".html":
        if isinstance(parser, MochawesomeParser):
            report = parser.parse_html(input_dir)
        else:
            raise ValueError("HTML parsing is only supported for Mochawesome reports")
    elif input_path_obj.is_file():
        report = parser.parse_file(input_dir)
    elif input_path_obj.is_dir():
        report = parser.parse_directory(input_dir)
    else:
        raise FileNotFoundError(f"Input path not found: {input_dir}")

    report.environment = config.environment
    summary = report.summary()
    logger.info(
        f"  Parsed {summary['total_tests']} tests: "
        f"{summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['skipped']} skipped ({summary['pass_rate']}% pass rate)"
    )

    # ── Step 2: Extract Failures ──────────────────────────────────────────
    logger.info("Step 2/6: Extracting and classifying failures")
    extractor = FailureExtractor()
    failures = extractor.extract(report)
    for f in failures:
        logger.info(
            f"  [{f.suggested_priority}] {f.failure_category}: {f.test.title}"
        )

    # ── Step 3: Enrich with Azure DevOps ──────────────────────────────────
    ado_client = None
    if config.azure.is_configured:
        logger.info("Step 3/6: Fetching test case details from Azure DevOps")
        ado_client = AzureDevOpsClient(config.azure)
        for failure in failures:
            ado_client.enrich_failure_with_test_case(failure)
            if failure.ado_test_case_id:
                logger.info(
                    f"  Found ADO test case #{failure.ado_test_case_id} for: {failure.test.title}"
                )
    else:
        logger.info("Step 3/6: Azure DevOps not configured — skipping enrichment")

    # ── Step 4: Enhance with Gemini AI ────────────────────────────────────
    gemini_client = GeminiAIClient(config.gemini)
    executive_summary = ""

    if config.gemini.is_configured:
        logger.info("Step 4/6: Enhancing failures with Gemini AI")
        bug_template = ""
        if config.bug_template_path:
            template_path = Path(config.bug_template_path)
            if template_path.exists():
                bug_template = template_path.read_text(encoding="utf-8")

        for failure in failures:
            gemini_client.enhance_failure(failure, bug_template)
            if failure.ai_summary:
                logger.info(f"  AI summary for: {failure.test.title}")

        # Generate executive summary
        executive_summary = gemini_client.generate_executive_summary(
            total=summary["total_tests"],
            passed=summary["passed"],
            failed=summary["failed"],
            skipped=summary["skipped"],
            failures=failures,
            environment=config.environment,
        )
    else:
        logger.info("Step 4/6: Gemini AI not configured — skipping AI enhancement")

    # ── Step 5: Generate HTML Report ──────────────────────────────────────
    logger.info("Step 5/6: Generating HTML report")
    html_gen = HTMLReportGenerator()
    html_output = os.path.join(
        config.report_output_dir, f"test-report-{timestamp}.html"
    )
    html_gen.generate(
        report=report,
        failures=failures,
        output_path=html_output,
        project_name=config.project_name,
        environment=config.environment,
        executive_summary=executive_summary,
    )
    logger.info(f"  HTML report: {html_output}")

    # ── Step 6: Generate Bug Tickets ──────────────────────────────────────
    bug_tickets = []
    if failures:
        logger.info(f"Step 6/6: Generating {len(failures)} bug ticket(s) → {config.bug_target}")
        bug_gen = BugTicketGenerator(config, ado_client)
        bug_tickets = bug_gen.generate_all(failures)

        # Write summary JSON
        bugs_summary_path = os.path.join(
            config.bug_output_dir, f"bugs-summary-{timestamp}.json"
        )
        bug_gen.generate_summary_json(bug_tickets, bugs_summary_path)
        logger.info(f"  Bug tickets summary: {bugs_summary_path}")
    else:
        logger.info("Step 6/6: No failures — no bug tickets generated")

    # ── Done ──────────────────────────────────────────────────────────────
    result = {
        "summary": summary,
        "failures_count": len(failures),
        "html_report": html_output,
        "bug_tickets": len(bug_tickets),
        "ai_enhanced": config.gemini.is_configured,
        "ado_enriched": config.azure.is_configured,
    }

    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info(f"  Tests: {summary['total_tests']} | Pass rate: {summary['pass_rate']}%")
    logger.info(f"  Failures: {len(failures)} | Bug tickets: {len(bug_tickets)}")
    logger.info(f"  HTML Report: {html_output}")
    logger.info("=" * 60)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test Report Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Parse Mochawesome JSON reports from default location
  python main.py

  # Parse from specific directory
  python main.py --input ./reports/.jsons

  # Parse the Mochawesome HTML report directly
  python main.py --input ./reports/index.html --parse-html

  # Use Playwright reports
  python main.py --framework playwright --input ./test-results

  # Full pipeline with AI and Azure DevOps
  python main.py --env-file .env --bug-target azure

  # Generate only HTML report (no AI/ADO)
  python main.py --html-only
        """,
    )

    parser.add_argument(
        "--input", "-i",
        help="Path to report file or directory (default: ./input)",
    )
    parser.add_argument(
        "--framework", "-f",
        choices=["mochawesome", "cypress", "playwright", "pytest", "selenium"],
        default="mochawesome",
        help="Test framework report format (default: mochawesome)",
    )
    parser.add_argument(
        "--parse-html",
        action="store_true",
        help="Parse Mochawesome HTML file directly (extract embedded JSON)",
    )
    parser.add_argument(
        "--env-file", "-e",
        help="Path to .env file for configuration",
    )
    parser.add_argument(
        "--bug-target",
        choices=["file", "azure", "jira"],
        help="Where to create bug tickets (default: file)",
    )
    parser.add_argument(
        "--bug-template",
        help="Path to custom bug report template (markdown)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for reports and bugs",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Generate only HTML report, skip AI and ADO enrichment",
    )
    parser.add_argument(
        "--environment",
        default="QA",
        help="Test environment label (default: QA)",
    )
    parser.add_argument(
        "--project-name",
        default="Unified-Test-Automation",
        help="Project name for report header",
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.env_file)

    # Apply CLI overrides
    if args.framework:
        config.framework = args.framework
    if args.bug_target:
        config.bug_target = args.bug_target
    if args.bug_template:
        config.bug_template_path = args.bug_template
    if args.output:
        config.report_output_dir = os.path.join(args.output, "reports")
        config.bug_output_dir = os.path.join(args.output, "bugs")
    if args.environment:
        config.environment = args.environment
    if args.project_name:
        config.project_name = args.project_name
    if args.html_only:
        # Clear AI and ADO configs to skip enrichment
        config.gemini.api_key = ""
        config.azure.pat = ""

    try:
        result = run_pipeline(
            config,
            input_path=args.input or "",
            parse_html=args.parse_html,
        )
        sys.exit(0 if result["failures_count"] == 0 else 1)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(2)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
