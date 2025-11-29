import os
import unittest
import tempfile
from src.tools.edit_file import replace_in_file

class TestEditFile(unittest.TestCase):
    def setUp(self):
        # Create a temporary file
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test_design.v")
        
        self.original_content = """module counter(
    input clk,
    input rst,
    output [7:0] count
);
    reg [7:0] count_reg;
    assign count = count_reg;
    
    always @(posedge clk or posedge rst) begin
        if (rst)
            count_reg <= 8'b0;
        else
            count_reg <= count_reg + 1;
    end
endmodule"""
        
        with open(self.test_file, "w") as f:
            f.write(self.original_content)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        os.rmdir(self.test_dir)

    def test_successful_replacement(self):
        target = "count_reg <= count_reg + 1;"
        replacement = "count_reg <= count_reg + 2; // Count by 2"
        
        result = replace_in_file(self.test_file, target, replacement)
        
        self.assertTrue(result["success"])
        
        with open(self.test_file, "r") as f:
            new_content = f.read()
            
        self.assertIn(replacement, new_content)
        self.assertNotIn(target, new_content)

    def test_target_not_found(self):
        target = "non_existent_code"
        replacement = "something_else"
        
        result = replace_in_file(self.test_file, target, replacement)
        
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"])

    def test_ambiguous_match(self):
        # Create content with duplicates
        content = "assign a = 1;\nassign a = 1;"
        with open(self.test_file, "w") as f:
            f.write(content)
            
        target = "assign a = 1;"
        replacement = "assign a = 2;"
        
        result = replace_in_file(self.test_file, target, replacement)
        
        self.assertFalse(result["success"])
        self.assertIn("found 2 times", result["message"])

if __name__ == "__main__":
    unittest.main()
