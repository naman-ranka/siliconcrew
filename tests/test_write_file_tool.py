from pathlib import Path

from src.tools.wrappers import write_file


def test_write_file_schema_exposes_field_descriptions():
    schema = write_file.args_schema.model_json_schema()
    props = schema["properties"]

    assert "description" in props["filename"]
    assert "workspace" in props["filename"]["description"].lower()
    assert "description" in props["content"]
    assert "full text" in props["content"]["description"].lower()


def test_write_file_missing_content_is_recoverable_error(monkeypatch):
    workspace = Path(__file__).resolve().parents[1] / "workspace" / "test_write_file_tool"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "dot_product_tb.v"
    if target.exists():
        target.unlink()

    monkeypatch.setenv("RTL_WORKSPACE", str(workspace))

    result = write_file.invoke({"filename": "dot_product_tb.v"})

    assert "Missing required argument 'content'" in result
    assert not target.exists()
