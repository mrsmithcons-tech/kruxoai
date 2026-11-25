import subprocess
import os
import sys

PLUGIN = {
    "name": "advanced_visual_element_detection",
    "description": "Adopted capability from open-interpreter: Local code execution, system shell automation, multi-language scripting.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "language": {
                "type": "STRING",
                "description": "The programming language or shell to use (e.g., 'python', 'bash', 'cmd', 'powershell')"
            },
            "code": {
                "type": "STRING",
                "description": "The code or commands to execute"
            }
        },
        "required": ["language", "code"]
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        language = parameters.get("language", "").lower()
        code = parameters.get("code", "")
        
        if not code:
            return "No code provided to execute."

        output = ""
        error = ""

        if player:
            player.write_log(f"Executing {language} code...")

        if language == "python":
            # Execute Python code in a subprocess to avoid blocking main process
            # and to maintain independence.
            process = subprocess.Popen(
                [sys.executable, "-c", code],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output, error = process.communicate()

        elif language in ["cmd", "powershell", "bash", "shell"]:
            if language == "bash":
                # Check for bash, usually available via Git or WSL on Windows
                cmd = ["bash", "-c", code]
            elif language == "powershell":
                cmd = ["powershell", "-Command", code]
            else:
                # Default to cmd
                cmd = ["cmd", "/c", code]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output, error = process.communicate()
            
        else:
            return f"Unsupported language: {language}"

        result_display = f"Language: {language}\n\nCode:\n{code}\n\nOutput:\n{output}\n\nErrors:\n{error}"
        
        if player:
            player.show_content("Code Execution Result", result_display)
            player.write_log(f"Execution finished. Output length: {len(output)}")

        if error:
            return f"Code execution finished with errors."
        return f"Code execution completed successfully."

    except Exception as e:
        if player:
            player.write_log(f"Fatal error in code execution: {str(e)}")
        return f"Code execution failed due to an unexpected error."