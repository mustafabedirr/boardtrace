from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_repository_file(relative_path: str) -> str:
    path = ROOT / relative_path
    assert path.is_file(), f"Expected repository file: {relative_path}"
    return path.read_text(encoding="utf-8")


def test_required_repository_documents_exist() -> None:
    for relative_path in (
        "AGENTS.md",
        ".env.example",
        "docs/security/live-analysis-lock.md",
    ):
        assert (ROOT / relative_path).is_file()


def test_security_document_contains_required_lifecycle_states() -> None:
    security_document = read_repository_file("docs/security/live-analysis-lock.md")

    for state in (
        "CREATED",
        "CAPTURING",
        "FINISH_PENDING",
        "FINISHED",
        "DEEP_ANALYSIS_RUNNING",
        "ANALYSIS_AVAILABLE",
        "FAILED",
    ):
        assert state in security_document


def test_environment_template_has_no_obvious_production_secret() -> None:
    environment_template = read_repository_file(".env.example")

    assert "sk_live_" not in environment_template
    assert "AKIA" not in environment_template


def test_package_manager_matches_the_approved_pnpm_version() -> None:
    package_metadata = read_repository_file("package.json")

    assert '"packageManager": "pnpm@11.11.0"' in package_metadata
