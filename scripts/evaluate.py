"""Run the offline On-Call Copilot evaluation harness."""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from oncall_app.evaluation.runner import format_report, run_evaluation  # noqa: E402


def main() -> None:
    """Print evaluation metrics."""
    print(format_report(run_evaluation()))


if __name__ == "__main__":
    main()
