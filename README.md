# Test Report Processing Pipeline

A Python-based pipeline that processes JSON test reports from **Cypress (Mochawesome)**, **Playwright**, or **Selenium/Pytest**, identifies failures, enriches them with AI and Azure DevOps data, and generates clean HTML reports with pre-formatted bug tickets.

## Architecture

```
report-pipeline/
├── main.py                     # CLI entry point & pipeline orchestrator
├── config.py                   # Configuration (env vars / .env file)
├── parsers/
│   ├── base_parser.py          # Shared data models (TestResult, TestSuite, TestReport)
│   ├── mochawesome.py          # Cypress Mochawesome JSON/HTML parser
│   ├── playwright.py           # Playwright JSON reporter parser
│   └── pytest_parser.py        # Pytest-json-report parser (Selenium)
├── extractors/
│   └── failure_extractor.py    # Failure classification & metadata extraction
├── integrations/
│   ├── azure_devops.py         # Azure DevOps REST API (test cases + bug creation)
│   └── gemini_ai.py            # Google Gemini API (AI summaries & bug descriptions)
├── generators/
│   ├── html_report.py          # Interactive HTML report generator
│   └── bug_ticket.py           # Bug ticket generator (file / Azure / JIRA)
├── .env.example                # Configuration template
└── requirements.txt            # Python dependencies (stdlib only!)
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-framework parsing** | Mochawesome (Cypress), Playwright JSON, Pytest JSON |
| **HTML report parsing** | Can extract embedded JSON from Mochawesome HTML reports |
| **Failure classification** | Auto-categorizes errors (Network, Timeout, Assertion, Auth, etc.) |
| **Priority assignment** | Suggests Critical/High/Medium/Low based on error type |
| **Azure DevOps integration** | Fetches test case repro steps; creates Bug work items |
| **Gemini AI enhancement** | AI-generated failure summaries, root cause analysis, bug descriptions |
| **Executive summary** | AI-generated overview of the test run |
| **HTML report** | Interactive dark-themed report with filters, search, and stats |
| **Bug tickets** | Markdown files, Azure DevOps bugs, or JIRA (placeholder) |
| **Zero dependencies** | Uses only Python 3.10+ standard library |

## Quick Start

### 1. Basic Usage (No AI/ADO — just parse and report)

```bash
cd report-pipeline

# Copy report files into ./input/ (or point --input to their location)
# e.g. copy your Mochawesome JSON/HTML reports into ./input/

# Parse Mochawesome JSON reports from the default input directory (./input)
python main.py --html-only

# Parse a Mochawesome HTML report directly
python main.py --input path/to/reports/index.html --parse-html --html-only

# Parse from a specific directory
python main.py --input path/to/reports/.jsons --html-only
```

### 2. Full Pipeline (with AI + Azure DevOps)

```bash
# Copy and configure .env
copy .env.example .env
# Edit .env with your API keys

# Run with all features
python main.py --env-file .env

# Auto-create bugs in Azure DevOps
python main.py --env-file .env --bug-target azure
```

### 3. Different Frameworks

```bash
# Playwright
python main.py --framework playwright --input ./test-results

# Pytest/Selenium
python main.py --framework pytest --input ./reports/pytest-report.json
```

## CLI Options

```
usage: main.py [-h] [--input INPUT] [--framework {mochawesome,cypress,playwright,pytest,selenium}]
               [--parse-html] [--env-file ENV_FILE] [--bug-target {file,azure,jira}]
               [--bug-template BUG_TEMPLATE] [--output OUTPUT] [--html-only]
               [--environment ENVIRONMENT] [--project-name PROJECT_NAME]

Options:
  --input, -i         Path to report file or directory
  --framework, -f     Report format (default: mochawesome)
  --parse-html        Parse Mochawesome HTML directly
  --env-file, -e      Path to .env configuration file
  --bug-target        Where to create bugs: file, azure, jira (default: file)
  --bug-template      Custom bug template (markdown) from your manual team
  --output, -o        Output directory for reports and bugs
  --html-only         Skip AI and ADO enrichment
  --environment       Test environment label (default: QA)
  --project-name      Project name for report header
```

## Configuration

Configuration is loaded from environment variables. You can use a `.env` file:

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_DEVOPS_ORG` | Azure DevOps organization name | For ADO features |
| `AZURE_DEVOPS_PROJECT` | Azure DevOps project name | For ADO features |
| `AZURE_DEVOPS_PAT` | Azure DevOps Personal Access Token | For ADO features |
| `GEMINI_API_KEY` | Google Gemini API key | For AI features |
| `GEMINI_MODEL` | Gemini model (default: gemini-2.0-flash) | No |
| `BUG_TARGET` | file / azure / jira | No |
| `BUG_TEMPLATE_PATH` | Custom bug template from manual QA team | No |
| `TEST_ENVIRONMENT` | Environment label (QA, Staging, etc.) | No |
| `PROJECT_NAME` | Project name for reports | No |

## Custom Bug Template

Get a bug reporting template from your manual QA team and save it as a markdown file. Then pass it to the pipeline:

```bash
python main.py --bug-template ./templates/our-bug-template.md --env-file .env
```

The AI will use your team's template structure when generating bug descriptions.

## Output

### HTML Report
- Interactive dark-themed dashboard
- Health indicator (Healthy / Needs Attention / Critical)
- Progress bar with pass/fail/skip breakdown
- AI-generated executive summary (when configured)
- Detailed failure cards with:
  - Error classification & priority
  - AI analysis & root cause (when configured)
  - Azure DevOps test case links (when configured)
  - Expandable stack traces
- Filterable/searchable test table

### Bug Tickets
- **File mode**: Markdown files in `output/bugs/` — ready for manual JIRA/ADO entry
- **Azure mode**: Automatically creates Bug work items in Azure DevOps
- **JIRA mode**: Placeholder for JIRA REST API integration

## Pipeline Flow

```
┌─────────────────┐
│  JSON/HTML       │
│  Test Reports    │
└────────┬────────┘
         │
    ┌────▼─────┐
    │  Parser   │  Mochawesome / Playwright / Pytest
    └────┬─────┘
         │
    ┌────▼──────────┐
    │  Failure       │  Classify errors, extract metadata
    │  Extractor     │  Assign priority & category
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Azure DevOps  │  Fetch test case repro steps
    │  (optional)    │  Match by test ID or title search
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Gemini AI     │  Generate failure summaries
    │  (optional)    │  Root cause analysis
    └────┬──────────┘  Executive summary
         │
    ┌────▼──────────┐     ┌────────────────┐
    │  HTML Report   │     │  Bug Tickets    │
    │  Generator     │     │  Generator      │
    └───────────────┘     └────────────────┘
         │                        │
    ┌────▼────┐           ┌──────▼───────┐
    │  .html  │           │  .md / ADO   │
    └─────────┘           └──────────────┘
```

## Integration with CI/CD

Add to your pipeline after test execution. Copy/point to the report files:

```yaml
# Azure DevOps Pipeline example
- script: |
    python report-pipeline/main.py --input $(Build.SourcesDirectory)/reports --parse-html --env-file .env --bug-target azure
  displayName: 'Process Test Reports'
  condition: always()  # Run even if tests fail
  env:
    GEMINI_API_KEY: $(GEMINI_API_KEY)
    AZURE_DEVOPS_PAT: $(System.AccessToken)
```

```bash
# Or as a post-test step in any project
python path/to/report-pipeline/main.py --input ./test-reports --html-only
```
