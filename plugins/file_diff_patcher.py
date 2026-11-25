import os
import subprocess
import json

PLUGIN = {
    "name": "file_diff_patcher",
    "description": "Adopted capability from open-interpreter: Local code execution, system shell automation, multi-language scripting",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "language": {
                "type": "STRING",
                "description": "The language of the code to execute (e.g., python, bash, powershell)"
            },
            "code": {
                "type": "STRING",
                "description": "The code to execute locally on the system"
            }
        },
        "required": ["language", "code"]
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    language = parameters.get("language", "").lower()
    code = parameters.get("code", "")
    
    if not code:
        return "No code provided to execute."

    if player:
        player.write_log(f"Executing {language} code...")

    result_text = ""
    exit_code = 0

    try:
        if language == "python":
            # Execute Python code in isolation? For now, run directly.
            # Capturing stdout/stderr
            import sys
            import io
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            redirected_output = sys.stdout = io.StringIO()
            redirected_error = sys.stderr = io.StringIO()
            
            exec_globals = {}
            try:
                exec(code, exec_globals)
                result_text = redirected_output.getvalue()
                error_text = redirected_error.getvalue()
                if error_text:
                    result_text += "\nErrors:\n" + error_text
            except Exception as e:
                result_text = redirected_output.getvalue() + "\nExecution Exception:\n" + str(e)
                exit_code = 1
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        elif language in ["bash", "sh", "powershell", "cmd", "batch"]:
            current_os = os.name
            if current_os == 'nt': # Windows
                if language in ["bash", "sh"]:
                    # Try git bash or wsl
                    cmd = ["bash", "-c", code]
                elif language == "powershell":
                    cmd = ["powershell", "-Command", code]
                else: # cmd/batch
                    cmd = ["cmd", "/c", code]
            else: # Unix-like (fallback, though prompt says Windows)
                if language == "powershell":
                    cmd = ["pwsh", "-Command", code]
                else:
                    cmd = ["/bin/bash", "-c", code]
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True if current_os == 'nt' and language in ["cmd", "batch"] else False
            )
            result_text = process.stdout
            if process.stderr:
                result_text += "\nErrors:\n" + process.stderr
            exit_code = process.returncode

        else:
            return f"Unsupported language: {language}"

    except Exception as e:
        result_text = f"An unexpected error occurred during execution: {str(e)}"
        exit_code = 1

    if player:
        summary = f"Code execution complete (Exit Code: {exit_code})."
        player.show_content(f"Execution Output ({language})", result_text)
        return summary
    else:
        return f"Execution result:\n{result_text}"