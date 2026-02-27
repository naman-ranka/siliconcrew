import json
import os
import tempfile

from src.tools.wrappers import apply_patch_tool


def test_apply_patch_tool_updates_file_with_unified_diff():
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            path = os.path.join(workspace, "design.v")
            with open(path, "w", encoding="utf-8") as f:
                f.write("module a;\nendmodule\n")

            patch = (
                "--- a/design.v\n"
                "+++ b/design.v\n"
                "@@ -1,2 +1,2 @@\n"
                "-module a;\n"
                "+module b;\n"
                " endmodule\n"
            )
            out = apply_patch_tool.invoke({"unified_diff": patch})
            data = json.loads(out)
            assert data["success"] is True
            assert "design.v" in data["files_changed"]

            with open(path, "r", encoding="utf-8") as f:
                new_text = f.read()
            assert "module b;" in new_text
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old

