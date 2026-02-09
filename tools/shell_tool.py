from agent_network.tools.base_tool import BaseTool
import subprocess
import shlex # NEW: Import shlex for safe command splitting

class RunShellCommandTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="run_shell_command",
            description="Executes a shell command and returns its stdout and stderr. Takes 'command' as argument."
        )

    def run(self, command: str):
        try:
            # Safely split the command string into a list of arguments
            cmd_list = shlex.split(command)
            
            result = subprocess.run(
                cmd_list, # Pass as list
                shell=False, # Crucially set to False to prevent shell injection
                capture_output=True,
                text=True,
                check=True
            )
            return {
                "status": "success",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "exit_code": result.returncode
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Command failed with exit code {e.returncode}",
                "stdout": e.stdout.strip(),
                "stderr": e.stderr.strip(),
                "exit_code": e.returncode
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
