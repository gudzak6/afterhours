"""The active application calls Gemini only."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    ROOT / "backend" / "app",
    ROOT / "backend" / "tests",
    ROOT / "frontend" / "src",
)
FORBIDDEN = (
    "from openai",
    "import openai",
    "OpenAI(",
    "api.openai.com",
    "openai_api_key",
    "OPENAI_API_KEY",
    "openai_not_configured",
    "chat.completions",
    "responses.create",
)


def test_active_code_does_not_call_openai() -> None:
    hits: list[str] = []
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or path.name == "test_no_openai.py":
                continue
            text = path.read_text()
            for item in FORBIDDEN:
                if item in text:
                    hits.append(f"{path.relative_to(ROOT)}: {item}")
    assert hits == []


def test_project_dependencies_do_not_require_openai() -> None:
    text = (ROOT / "backend" / "pyproject.toml").read_text()
    assert "openai" not in text
    assert "google-genai" in text
