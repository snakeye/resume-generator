from resume_generator.pipeline import PIPELINE_STAGE_NAMES
from resume_generator.trace import ConsoleTracer


def test_default_trace_reports_stage_and_safe_summary():
    output = []
    tracer = ConsoleTracer(output=output.append)

    tracer.stage("started", "20-vacancy", None, None)
    tracer.stage(
        "completed",
        "20-vacancy",
        {
            "role": "Engineer",
            "requirements": [{"priority": "must_have"}, {"priority": "important"}],
            "secret": "do not print",
        },
        0.2,
    )

    assert output == [
        "[2/12] Analyzing vacancy...",
        "       2 requirements: 1 must-have, 1 important",
    ]
    assert "secret" not in "\n".join(output)


def test_quiet_trace_suppresses_progress_but_keeps_final_results():
    output = []
    tracer = ConsoleTracer(quiet=True, output=output.append)

    tracer.message("stage started")
    tracer.stage("started", PIPELINE_STAGE_NAMES[0], None, None)
    tracer.result("Queue is empty")

    assert output == ["Queue is empty"]


def test_debug_trace_includes_elapsed_time():
    output = []
    tracer = ConsoleTracer(debug=True, output=output.append)

    tracer.stage("started", "10-input", None, None)
    tracer.stage("completed", "10-input", {}, 0.4)

    assert output[-1] == "       Request stored (0.4s)"
