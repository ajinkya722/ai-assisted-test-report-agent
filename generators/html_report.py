"""
HTML report generator — produces a clean, interactive HTML report with
execution insights, failure details, and AI-enhanced summaries.
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from parsers.base_parser import TestReport
from extractors.failure_extractor import FailureDetail


class HTMLReportGenerator:
    """Generates a standalone HTML report from parsed test data."""

    def generate(
        self,
        report: TestReport,
        failures: list[FailureDetail],
        output_path: str,
        project_name: str = "",
        environment: str = "",
        executive_summary: str = "",
    ) -> str:
        """Generate HTML report and write to file. Returns the output path."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        summary = report.summary()
        all_tests = report.all_tests

        html_content = self._build_html(
            summary=summary,
            all_tests=all_tests,
            failures=failures,
            project_name=project_name,
            environment=environment,
            executive_summary=executive_summary,
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path

    def _build_html(
        self,
        summary: dict[str, Any],
        all_tests: list,
        failures: list[FailureDetail],
        project_name: str,
        environment: str,
        executive_summary: str,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pass_rate = summary.get("pass_rate", 0)
        total = summary.get("total_tests", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)

        # Determine health color
        if pass_rate >= 95:
            health_color = "#22c55e"
            health_label = "Healthy"
        elif pass_rate >= 80:
            health_color = "#f59e0b"
            health_label = "Needs Attention"
        else:
            health_color = "#ef4444"
            health_label = "Critical"

        # Build failure rows
        failure_rows = ""
        for i, f in enumerate(failures, 1):
            priority_color = {
                "Critical": "#ef4444",
                "High": "#f97316",
                "Medium": "#f59e0b",
                "Low": "#22c55e",
            }.get(f.suggested_priority, "#94a3b8")

            err_msg = html.escape(f.test.error_message[:200])
            ai_summary_html = ""
            if f.ai_summary:
                ai_summary_html = f"""
                <div class="ai-badge">
                    <span class="ai-icon">&#x2728;</span>
                    <strong>AI Analysis:</strong> {html.escape(f.ai_summary)}
                </div>"""

            ai_root_cause_html = ""
            if f.ai_root_cause:
                ai_root_cause_html = f"""
                <div class="ai-badge root-cause">
                    <span class="ai-icon">&#x1F50D;</span>
                    <strong>Root Cause:</strong> {html.escape(f.ai_root_cause)}
                </div>"""

            stack_html = ""
            if f.test.error_stack:
                escaped_stack = html.escape(f.test.error_stack[:1500])
                stack_html = f"""
                <details class="stack-trace">
                    <summary>Stack Trace</summary>
                    <pre>{escaped_stack}</pre>
                </details>"""

            ado_html = ""
            if f.ado_test_case_id:
                ado_html = f"""
                <div class="ado-info">
                    <strong>ADO Test Case:</strong> #{html.escape(f.ado_test_case_id)} — {html.escape(f.ado_test_case_title)}
                </div>"""

            failure_rows += f"""
            <div class="failure-card">
                <div class="failure-header">
                    <span class="failure-num">#{i}</span>
                    <span class="failure-title">{html.escape(f.test.title)}</span>
                    <span class="priority-badge" style="background:{priority_color}">{html.escape(f.suggested_priority)}</span>
                    <span class="category-badge">{html.escape(f.failure_category)}</span>
                </div>
                <div class="failure-meta">
                    <span>&#x1F4C1; {html.escape(f.test.file_path)}</span>
                    <span>&#x23F1; {f.test.duration_display}</span>
                    <span>&#x1F3AF; {html.escape(f.affected_component)}</span>
                </div>
                <div class="error-msg"><code>{err_msg}</code></div>
                {ai_summary_html}
                {ai_root_cause_html}
                {ado_html}
                {stack_html}
            </div>"""

        # Build all-tests table rows
        test_table_rows = ""
        for t in all_tests:
            state_class = {
                "passed": "state-passed",
                "failed": "state-failed",
                "pending": "state-skipped",
                "skipped": "state-skipped",
            }.get(t.state, "")
            state_icon = {
                "passed": "&#x2705;",
                "failed": "&#x274C;",
                "pending": "&#x23F8;",
                "skipped": "&#x23ED;",
            }.get(t.state, "&#x2753;")

            test_table_rows += f"""
            <tr class="{state_class}">
                <td>{state_icon} {html.escape(t.state.upper())}</td>
                <td title="{html.escape(t.full_title)}">{html.escape(t.title)}</td>
                <td>{html.escape(t.suite_name)}</td>
                <td>{t.duration_display}</td>
                <td class="error-cell">{html.escape(t.error_message[:100]) if t.error_message else '—'}</td>
            </tr>"""

        # Executive summary section
        exec_summary_html = ""
        if executive_summary:
            exec_summary_html = f"""
        <section class="section">
            <h2>&#x1F4CA; Executive Summary <span class="ai-tag">AI Generated</span></h2>
            <div class="executive-summary">{html.escape(executive_summary)}</div>
        </section>"""

        # Duration display
        total_dur_ms = summary.get("total_duration_ms", 0)
        if total_dur_ms >= 3600000:
            hours = total_dur_ms // 3600000
            mins = (total_dur_ms % 3600000) // 60000
            duration_str = f"{hours}h {mins}m"
        elif total_dur_ms >= 60000:
            mins = total_dur_ms // 60000
            secs = (total_dur_ms % 60000) // 1000
            duration_str = f"{mins}m {secs}s"
        else:
            duration_str = f"{total_dur_ms / 1000:.1f}s"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(project_name)} — Test Report</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface2: #334155;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
            --accent: #3b82f6;
            --green: #22c55e;
            --red: #ef4444;
            --yellow: #f59e0b;
            --orange: #f97316;
            --border: #475569;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, var(--surface) 0%, #1a2744 100%);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
        }}
        .header h1 {{
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .header-meta {{
            display: flex;
            gap: 2rem;
            color: var(--text-muted);
            font-size: 0.9rem;
            flex-wrap: wrap;
        }}

        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
        }}
        .stat-card .stat-value {{
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1;
        }}
        .stat-card .stat-label {{
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 0.3rem;
        }}
        .stat-passed .stat-value {{ color: var(--green); }}
        .stat-failed .stat-value {{ color: var(--red); }}
        .stat-skipped .stat-value {{ color: var(--yellow); }}
        .stat-total .stat-value {{ color: var(--accent); }}
        .stat-health .stat-value {{ font-size: 1.5rem; }}

        /* Progress bar */
        .progress-container {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .progress-bar {{
            height: 24px;
            border-radius: 12px;
            overflow: hidden;
            display: flex;
            background: var(--surface2);
        }}
        .progress-passed {{ background: var(--green); }}
        .progress-failed {{ background: var(--red); }}
        .progress-skipped {{ background: var(--yellow); }}
        .progress-labels {{
            display: flex;
            justify-content: space-between;
            margin-top: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        /* Sections */
        .section {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .section h2 {{
            font-size: 1.3rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        /* Executive summary */
        .executive-summary {{
            background: var(--surface2);
            border-radius: 8px;
            padding: 1rem;
            font-style: italic;
            color: var(--text);
            line-height: 1.8;
            white-space: pre-line;
        }}

        /* Failure cards */
        .failure-card {{
            background: var(--surface2);
            border: 1px solid var(--border);
            border-left: 4px solid var(--red);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        .failure-header {{
            display: flex;
            align-items: center;
            gap: 0.7rem;
            flex-wrap: wrap;
            margin-bottom: 0.5rem;
        }}
        .failure-num {{
            background: var(--red);
            color: white;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: 700;
            flex-shrink: 0;
        }}
        .failure-title {{
            font-weight: 600;
            font-size: 1rem;
        }}
        .priority-badge, .category-badge {{
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .priority-badge {{ color: white; }}
        .category-badge {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-muted);
        }}
        .failure-meta {{
            display: flex;
            gap: 1.5rem;
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
        }}
        .error-msg {{
            background: #1c1c1c;
            border-radius: 6px;
            padding: 0.5rem 0.8rem;
            margin: 0.5rem 0;
            font-size: 0.85rem;
            overflow-x: auto;
        }}
        .error-msg code {{ color: #fca5a5; }}

        /* AI badges */
        .ai-badge {{
            background: linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%);
            border: 1px solid #3b82f6;
            border-radius: 8px;
            padding: 0.6rem 0.8rem;
            margin: 0.5rem 0;
            font-size: 0.85rem;
        }}
        .ai-badge.root-cause {{
            border-color: var(--orange);
            background: linear-gradient(135deg, #3d2a1a 0%, #1e293b 100%);
        }}
        .ai-icon {{ margin-right: 0.3rem; }}
        .ai-tag {{
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 600;
            vertical-align: middle;
        }}

        .ado-info {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin: 0.3rem 0;
        }}

        .stack-trace {{
            margin-top: 0.5rem;
        }}
        .stack-trace summary {{
            cursor: pointer;
            color: var(--text-muted);
            font-size: 0.8rem;
        }}
        .stack-trace pre {{
            background: #0d1117;
            color: #c9d1d9;
            border-radius: 6px;
            padding: 0.8rem;
            margin-top: 0.3rem;
            font-size: 0.75rem;
            overflow-x: auto;
            max-height: 300px;
            overflow-y: auto;
        }}

        /* Tests table */
        .tests-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        .tests-table th {{
            background: var(--surface2);
            padding: 0.7rem;
            text-align: left;
            border-bottom: 2px solid var(--border);
            position: sticky;
            top: 0;
        }}
        .tests-table td {{
            padding: 0.5rem 0.7rem;
            border-bottom: 1px solid var(--border);
        }}
        .tests-table tr.state-failed {{ background: rgba(239, 68, 68, 0.08); }}
        .tests-table tr.state-skipped {{ opacity: 0.65; }}
        .error-cell {{
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #fca5a5;
            font-size: 0.8rem;
        }}
        .table-wrapper {{
            max-height: 600px;
            overflow-y: auto;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}

        /* Filter controls */
        .filter-bar {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            background: var(--surface2);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.4rem 1rem;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{ border-color: var(--accent); }}
        .filter-btn.active {{ background: var(--accent); border-color: var(--accent); }}
        .search-input {{
            background: var(--surface2);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.4rem 1rem;
            border-radius: 20px;
            font-size: 0.8rem;
            width: 250px;
        }}
        .search-input::placeholder {{ color: var(--text-muted); }}

        /* Footer */
        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.8rem;
            padding: 1rem;
            margin-top: 1rem;
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            body {{ padding: 1rem; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .header-meta {{ flex-direction: column; gap: 0.5rem; }}
        }}
    </style>
</head>
<body>
<div class="container">

    <!-- Header -->
    <div class="header">
        <h1>&#x1F9EA; {html.escape(project_name) or 'Test Execution'} Report</h1>
        <div class="header-meta">
            <span>&#x1F4C5; {timestamp}</span>
            <span>&#x1F3E0; {html.escape(environment) or 'N/A'}</span>
            <span>&#x2699;&#xFE0F; {html.escape(summary.get('framework', ''))}</span>
            <span>&#x23F1; {duration_str}</span>
            <span>&#x1F4C8; Pass Rate: {pass_rate:.1f}%</span>
        </div>
    </div>

    <!-- Stats Cards -->
    <div class="stats-grid">
        <div class="stat-card stat-total">
            <div class="stat-value">{total}</div>
            <div class="stat-label">Total Tests</div>
        </div>
        <div class="stat-card stat-passed">
            <div class="stat-value">{passed}</div>
            <div class="stat-label">Passed</div>
        </div>
        <div class="stat-card stat-failed">
            <div class="stat-value">{failed}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card stat-skipped">
            <div class="stat-value">{skipped}</div>
            <div class="stat-label">Skipped</div>
        </div>
        <div class="stat-card stat-health">
            <div class="stat-value" style="color: {health_color}">{health_label}</div>
            <div class="stat-label">Health Status</div>
        </div>
    </div>

    <!-- Progress Bar -->
    <div class="progress-container">
        <div class="progress-bar">
            <div class="progress-passed" style="width: {(passed/total*100) if total else 0}%"></div>
            <div class="progress-failed" style="width: {(failed/total*100) if total else 0}%"></div>
            <div class="progress-skipped" style="width: {(skipped/total*100) if total else 0}%"></div>
        </div>
        <div class="progress-labels">
            <span>&#x2705; Passed: {passed} ({(passed/total*100) if total else 0:.1f}%)</span>
            <span>&#x274C; Failed: {failed} ({(failed/total*100) if total else 0:.1f}%)</span>
            <span>&#x23F8; Skipped: {skipped} ({(skipped/total*100) if total else 0:.1f}%)</span>
        </div>
    </div>

    {exec_summary_html}

    <!-- Failures Section -->
    {"" if not failures else f'''
    <section class="section">
        <h2>&#x274C; Failed Tests ({len(failures)})</h2>
        {failure_rows}
    </section>
    '''}

    <!-- All Tests Table -->
    <section class="section">
        <h2>&#x1F4CB; All Tests ({total})</h2>
        <div class="filter-bar">
            <button class="filter-btn active" onclick="filterTable('all')">All ({total})</button>
            <button class="filter-btn" onclick="filterTable('passed')">&#x2705; Passed ({passed})</button>
            <button class="filter-btn" onclick="filterTable('failed')">&#x274C; Failed ({failed})</button>
            <button class="filter-btn" onclick="filterTable('skipped')">&#x23F8; Skipped ({skipped})</button>
            <input type="text" class="search-input" placeholder="Search tests..." oninput="searchTable(this.value)">
        </div>
        <div class="table-wrapper">
            <table class="tests-table" id="testsTable">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Test Name</th>
                        <th>Suite</th>
                        <th>Duration</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {test_table_rows}
                </tbody>
            </table>
        </div>
    </section>

    <div class="footer">
        Generated by Test Report Pipeline &mdash; {timestamp}
    </div>
</div>

<script>
function filterTable(state) {{
    const rows = document.querySelectorAll('#testsTable tbody tr');
    const buttons = document.querySelectorAll('.filter-btn');
    buttons.forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    rows.forEach(row => {{
        if (state === 'all') {{ row.style.display = ''; return; }}
        const match = row.classList.contains('state-' + state);
        row.style.display = match ? '' : 'none';
    }});
}}
function searchTable(query) {{
    const rows = document.querySelectorAll('#testsTable tbody tr');
    const q = query.toLowerCase();
    rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
    }});
}}
</script>
</body>
</html>"""
