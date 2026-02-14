import logging
import requests
import time
from typing import Dict, Any, List
from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, tools: List[BaseTool], execution_mode: str = "safe", hub_url: str = None):
        # Convert list of tools to a dict keyed by tool name for lookup
        if isinstance(tools, list):
            self.tools = {tool.name: tool for tool in tools}
        else:
            self.tools = tools
        self.execution_mode = execution_mode
        self.dangerous_tools = ["run_shell_command", "write_file"]
        self.hub_url = hub_url or "http://127.0.0.1:5000"

    def execute(self, tool_name: str, **tool_args) -> Any:
        """
        Executes a tool by name with the given arguments.
        This is the simple execution path used by Agent._process_task_with_replanning.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found.")

        tool_instance = self.tools[tool_name]
        return tool_instance.run(**tool_args)

    def execute_step(self, agent_name: str, task: str, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single step of the plan using the appropriate tool.
        Handles approval flow for dangerous tools in safe mode.
        """
        tool_name = step.get("tool")
        tool_args = step.get("args", {})

        if tool_name not in self.tools:
            logger.error(f"Agent '{agent_name}' - Tool '{tool_name}' not found for task '{task}'.")
            return {"status": "error", "message": f"Tool '{tool_name}' not found."}

        if self.execution_mode == "safe" and tool_name in self.dangerous_tools:
            logger.info(f"Agent '{agent_name}' - Dangerous tool '{tool_name}' requires approval for task '{task}'.")

            # Request approval from the hub
            try:
                approval_payload = {
                    "agent_name": agent_name,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                }
                response = requests.post(f"{self.hub_url}/api/request_approval", json=approval_payload, timeout=10)
                response.raise_for_status()
                request_id = response.json().get("request_id")

                if not request_id:
                    return {"status": "error", "message": "Failed to get a valid approval request ID from the hub."}

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to request approval from hub: {e}")
                return {"status": "error", "message": f"Failed to request approval from hub: {e}"}

            # Poll for approval status
            timeout = 300 # 5 minutes
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    check_response = requests.get(f"{self.hub_url}/api/check_approval/{request_id}", timeout=10)
                    check_response.raise_for_status()
                    status_data = check_response.json()

                    if status_data["status"] == "approved":
                        logger.info(f"Approval received for request '{request_id}'. Executing tool '{tool_name}'.")
                        break # Exit loop and proceed with execution
                    elif status_data["status"] == "denied":
                        logger.warning(f"Execution of tool '{tool_name}' denied by user for request '{request_id}'.")
                        return {"status": "aborted", "message": "Execution denied by user."}

                    # If status is still "pending", wait and continue polling
                    time.sleep(5)

                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to check approval status from hub: {e}")
                    time.sleep(5) # Wait before retrying in case of network issues

            if time.time() - start_time >= timeout:
                logger.error(f"Approval for request '{request_id}' timed out after {timeout} seconds.")
                return {"status": "error", "message": "Approval request timed out."}

        tool_instance = self.tools[tool_name]
        try:
            # Pass agent_name to tools that might need it
            if "agent_name" in tool_instance.run.__code__.co_varnames:
                tool_args["agent_name"] = agent_name

            result = tool_instance.run(**tool_args)
            logger.info(f"Agent '{agent_name}' executed tool '{tool_name}' for task '{task}' with result: {result}")
            return result
        except Exception as e:
            logger.error(f"Agent '{agent_name}' - Error executing tool '{tool_name}' for task '{task}': {str(e)}", exc_info=True)
            return {"status": "error", "message": f"Error executing tool '{tool_name}': {str(e)}"}
