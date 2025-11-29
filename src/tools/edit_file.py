import os

def replace_in_file(file_path, target_text, replacement_text):
    """
    Replaces a specific block of text in a file with new content.
    
    Args:
        file_path (str): Absolute path to the file.
        target_text (str): The exact text block to find and replace.
        replacement_text (str): The new text to insert.
        
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "diff": str (optional)
        }
    """
    if not os.path.exists(file_path):
        return {"success": False, "message": f"File not found: {file_path}"}
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if target_text not in content:
            return {
                "success": False, 
                "message": "Target text not found in file. Ensure you copied the text exactly, including whitespace."
            }
            
        # Safety check: Ambiguous match
        if content.count(target_text) > 1:
            return {
                "success": False,
                "message": f"Target text found {content.count(target_text)} times. Please provide a more unique context block."
            }
            
        new_content = content.replace(target_text, replacement_text)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return {
            "success": True,
            "message": "Successfully replaced text.",
            "diff": f"- {target_text[:50]}...\n+ {replacement_text[:50]}..."
        }
        
    except Exception as e:
        return {"success": False, "message": f"Error editing file: {str(e)}"}
