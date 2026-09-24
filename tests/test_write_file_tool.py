from src.tools.wrappers import write_file


def test_write_file_schema_exposes_field_descriptions():
    schema = write_file.args_schema.model_json_schema()
    props = schema["properties"]

    assert "description" in props["filename"]
    assert "workspace" in props["filename"]["description"].lower()
    assert "description" in props["content"]
    assert "full text" in props["content"]["description"].lower()


def test_write_file_missing_content_is_recoverable_error(monkeypatch, tmp_path):
    workspace = tmp_path / "test_write_file_tool"
    workspace.mkdir()
    target = workspace / "dot_product_tb.v"

    monkeypatch.setenv("RTL_WORKSPACE", str(workspace))

    result = write_file.invoke({"filename": "dot_product_tb.v"})

    assert "Missing required argument 'content'" in result
    assert not target.exists()
