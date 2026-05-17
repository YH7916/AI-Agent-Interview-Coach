"""Run offline interview-agent evaluations."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from oncall_app.interview.evaluation import format_interview_report, run_interview_evaluation  # noqa: E402,I001


def main() -> None:
    """Print interview-agent evaluation metrics."""
    print(format_interview_report(run_interview_evaluation()))


if __name__ == "__main__":
    main()
