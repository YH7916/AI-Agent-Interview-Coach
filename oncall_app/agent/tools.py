"""Agent tool implementations."""

from oncall_app.agent.state import ToolObservation
from oncall_app.documents.repository import DocumentRepository
from oncall_app.models import ToolCall

PREVIEW_LIMIT = 240


class ReadFileTool:  # pylint: disable=too-few-public-methods
    """Safe implementation of readFile(fname)."""

    name = "readFile"

    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    def read_file(self, fname: str) -> ToolObservation:
        """Read one direct file name from the SOP data directory."""
        content = self.repository.read_file(fname)
        preview = content[:PREVIEW_LIMIT].replace("\n", " ")
        return ToolObservation(
            content=content,
            call=ToolCall(
                tool=self.name,
                fname=fname,
                result_preview=preview,
            ),
        )
