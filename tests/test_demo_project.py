import fitz

from backend.app.demo_project import (
    DEMO_PROJECT_ID,
    DEMO_SEED_ID,
    FIELD_TYPES,
    _extraction_for,
    build_demo_dataset,
    build_demo_pdf_bytes,
    ensure_demo_project,
    is_demo_project,
)


class _ExistingDemoCursor:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.statements.append((" ".join(query.split()), params))

    def fetchone(self):
        return ({"_demo": {"seed_id": DEMO_SEED_ID}},)


class _ExistingDemoConnection:
    def __init__(self):
        self.cursor_instance = _ExistingDemoCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


def test_demo_dataset_is_deterministic_and_coherent():
    first = build_demo_dataset()
    second = build_demo_dataset()

    assert first["project_id"] == DEMO_PROJECT_ID == second["project_id"]
    assert len(first["queries"]) == 3
    assert len(first["records"]) == 7
    assert len(first["papers"]) == 5
    assert len(first["golden_queries"]) == 5
    assert sum(item["action"] == "auto_merge" for item in first["records"]) == 2
    assert sum(bool(item.get("excluded")) for item in first["papers"]) == 1
    assert [item["id"] for item in first["papers"]] == [
        item["id"] for item in second["papers"]
    ]


def test_demo_extraction_has_one_literal_source_and_explicit_missing_fields():
    paper = next(item for item in build_demo_dataset()["papers"] if not item.get("excluded"))
    extraction = _extraction_for(paper)

    sourced_fields = [
        field_name
        for field_name in FIELD_TYPES
        if extraction[field_name]["evidence"]
    ]
    assert sourced_fields == [paper["evidence_field"]]
    assert extraction[paper["evidence_field"]]["evidence"][0]["quote"] == paper["quote"]
    assert extraction[paper["evidence_field"]]["evidence"][0]["chunk_id"] == paper["chunk_id"]
    assert extraction["_demo"]["evidence_card"] is True


def test_demo_pdf_is_readable_and_identifies_its_limited_scope():
    paper = next(item for item in build_demo_dataset()["papers"] if not item.get("excluded"))
    document = fitz.open(stream=build_demo_pdf_bytes(paper), filetype="pdf")
    content = " ".join(" ".join(page.get_text().split()) for page in document)
    document.close()

    assert len(content) > 200
    assert paper["doi"] in content
    assert paper["quote"] in content
    assert "não é o artigo integral" in content


def test_existing_demo_is_opened_without_reinserting_database_rows(tmp_path):
    connection = _ExistingDemoConnection()
    result = ensure_demo_project(
        connection_factory=lambda: connection,
        pdf_directory=tmp_path,
    )

    assert result["project_id"] == DEMO_PROJECT_ID
    assert result["created"] is False
    assert result["restored"] is False
    assert result["pdfs"]["created"] == 4
    assert len(connection.cursor_instance.statements) == 1
    assert connection.cursor_instance.statements[0][0].startswith(
        "SELECT criteria_jsonb FROM review_projects"
    )


def test_demo_marker_requires_the_official_seed_id():
    assert is_demo_project({"criteria_jsonb": {"_demo": {"seed_id": DEMO_SEED_ID}}})
    assert not is_demo_project({"criteria_jsonb": {"_demo": {"seed_id": "outro"}}})
    assert not is_demo_project(None)
