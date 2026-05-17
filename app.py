"""Entry point for the On-Call Copilot web application."""

import uvicorn

from oncall_app.api.app_factory import create_app

app = create_app()


def main():
    """Start the local development server."""
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
