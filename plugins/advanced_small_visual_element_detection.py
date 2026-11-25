import subprocess
import os

PLUGIN = {
    "name": "advanced_small_visual_element_detection",
    "description": "Adopted capability from open-interpreter: Local code execution, system shell automation, multi-language scripting",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "code": {
                "type": "STRING",
                "description": "The code to be executed locally."
            },
            "language": {
                "type": "STRING",
                "description": "The language of the code (e.g., python, bash, powershell)."
            }
        },
        "required": ["code", "language"]
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        code = parameters.get("code", "")
        language = parameters.get("language", "").lower()
        
        if not code:
            return "Execution failed: No code provided."

        output = ""
        error = ""

        if language in ["python", "py"]:
            if player:
                player.write_log(f"Executing local Python code.")
            process = subprocess.Popen(
                ["python", "-c", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            output, error = process.communicate()

        elif language in ["bash", "sh", "shell"]:
            if player:
                player.write_log(f"Executing system shell command.")
            process = subprocess.Popen(
                code,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            output, error = process.communicate()

        elif language in ["powershell", "ps1"]:
            if player:
                player.write_log(f"Executing PowerShell command.")
            process = subprocess.Popen(
                ["powershell", "-c", code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            output, error = process.communicate()
            
        else:
            return f"Execution failed: Unsupported language '{language}'."

        result_text = f"Output:\n{output}\nError:\n{error}"
        
        if player:
            player.show_content(f"Local Execution Result ({language})", result_text)
            
        return f"Successfully executed {language} code."

    except Exception as e:
        error_msg = f"Fatal error during execution: {str(e)}"
        if player:
            player.write_log(error_msg)
        return "Local code execution failed due to an error."