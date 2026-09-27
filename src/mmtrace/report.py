"""Report formatting helpers for MMTrace."""

from __future__ import annotations

from mmtrace.schema.finding import Report


def format_report(report: Report, output_format: str = "text") -> str:
    if output_format == "text":
        return format_text_report(report)
    if output_format == "json":
        return format_json_report(report)
    raise ValueError(f"unsupported report format: {output_format}")


def format_text_report(report: Report) -> str:
    lines = [
        "MMTrace Reliability Report",
        "",
        f"Trace: {report.trace_id}",
        f"Status: {report.status.value}",
        "",
        f"Errors: {report.error_count}",
        f"Warnings: {report.warning_count}",
        f"Info: {report.info_count}",
    ]

    if report.findings:
        lines.append("")
        for finding in report.findings:
            step = finding.step_id if finding.step_id is not None else "-"
            lines.append(
                f"{finding.severity.value:<7} {finding.rule_id:<10} Step {step}   {finding.title}"
            )

    return "\n".join(lines)


def format_json_report(report: Report) -> str:
    return report.model_dump_json(indent=2)


__all__ = ["format_json_report", "format_report", "format_text_report"]

