import json

from mmtrace.report import format_json_report, format_text_report
from mmtrace.schema.finding import Finding, Report, ReportStatus, Severity


def test_pass_report_text_output() -> None:
    report = Report.from_findings("trace-pass", [])

    output = format_text_report(report)

    assert "MMTrace Reliability Report" in output
    assert "Trace: trace-pass" in output
    assert "Status: PASS" in output
    assert "Errors: 0" in output
    assert "Warnings: 0" in output


def test_fail_report_text_output() -> None:
    report = Report.from_findings(
        "trace-fail",
        [
            Finding(
                rule_id="MMTRACE003",
                severity=Severity.ERROR,
                step_id="step-001",
                title="Coordinate Out Of Frame",
            )
        ],
    )

    output = format_text_report(report)

    assert "Status: FAIL" in output
    assert "Errors: 1" in output
    assert "ERROR   MMTRACE003 Step step-001" in output
    assert "Coordinate Out Of Frame" in output


def test_json_report_output_can_be_parsed_again() -> None:
    report = Report.from_findings(
        "trace-json",
        [
            Finding(
                rule_id="MMTRACE006",
                severity=Severity.WARNING,
                step_id="step-001",
                title="Missing Post-Action Verification",
            )
        ],
    )

    parsed = json.loads(format_json_report(report))

    assert parsed["trace_id"] == "trace-json"
    assert parsed["status"] == "PASS"
    assert parsed["warning_count"] == 1
    assert parsed["findings"][0]["rule_id"] == "MMTRACE006"


def test_report_counts_match_findings() -> None:
    report = Report.from_findings(
        "trace-counts",
        [
            Finding(rule_id="ERROR", severity=Severity.ERROR, title="Error"),
            Finding(rule_id="WARNING", severity=Severity.WARNING, title="Warning"),
            Finding(rule_id="INFO", severity=Severity.INFO, title="Info"),
        ],
    )

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.info_count == 1

