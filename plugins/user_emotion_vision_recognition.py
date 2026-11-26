import subprocess
import os

PLUGIN = {
    "name": "user_emotion_vision_recognition",
    "description": "Enables local code execution, system shell automation, and scripting across multiple languages.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "language": {
                "type": "STRING",
                "description": "The programming language or shell to execute (e.g., 'python', 'powershell', 'cmd', 'bash')."
            },
            "code": {
                "type": "STRING",
                "description": "The actual code or commands to execute on the local system."
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
            player.write_log(f"Executing {language} code.")

        if language == "python":
            # Execute Python code locally
            try:
                # Using a safe execution environment for user content isn't possible here
                # without heavy dependencies, executing directly as requested.
                exec_globals = {}
                exec(code, exec_globals)
                output = "Python code parsed and executed successfully."
                if exec_globals:
                    output += f" Result variables: {list(exec_globals.keys())}"
            except Exception as e:
                error = str(e)

        elif language in ["powershell", "cmd", "bash"]:
            # System shell execution
            shell_cmd = []
            if language == "powershell":
                shell_cmd = ["powershell", "-Command", code]
            elif language == "cmd":
                shell_cmd = ["cmd", "/c", code]
            elif language == "bash":
                shell_cmd = ["bash", "-c", code]
                
            process = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True # Required for shell commands on Windows
            )
            stdout, stderr = process.communicate()
            output = stdout
            error = stderr

        else:
            return f"Language '{language}' is not supported for execution."

        final_response = f"Output:\n{output}" if output else ""
        if error:
            final_response += f"\nError:\n{error}"

        if player:
            player.show_content(f"{language.capitalize()} Execution Result", final_response)
        
        return f"Executed {language} code complete."

    except Exception as e:
        if player:
            player.write_log(f"Critical error in execution plugin: {str(e)}")
        return f"An error occurred during execution: {str(e)}"