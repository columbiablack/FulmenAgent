import json
import logging
import os
import requests
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import sys
import subprocess

# Imports for internal components
from src.planner import Planner
from src.memory import Memory
from src.critic import Critic
from src.executor import Executor

# Imports for tools
from tools.base_tool import BaseTool
from tools.file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool
from tools.shell_tool import RunShellCommandTool
from tools.utility_tools import PrintTaskTool, WebFetchTool, ImageAnalysisTool, SendImageTool, ImageGenerationTool, FinishTaskTool, SendUserMessageTool, SendAgentMessageTool, LLMCallTool
from tools.email_tools import EmailCheckTool, EmailSendTool
from tools.calendar_tools import CalendarCheckTool, CalendarAddEventTool
from tools.voice_tools import MakePhoneCallTool, TranscribeVoiceTool, SynthesizeSpeechTool, ColdCallTool
from tools.contact_tools import AccessContactsTool

# Imports for Google Cloud credentials check for voice tools
import google.auth
from google.auth import exceptions as google_auth_exceptions

# Define a module-level logger
logger = logging.getLogger(__name__)

def _check_google_credentials() -> bool:
    """Checks if Google Cloud credentials are available."""
    try:
        credentials, project_id = google.auth.default()
        logger.info("Google Cloud credentials found.")
        return True
    except google_auth_exceptions.DefaultCredentialsError:
        logger.warning("Google Cloud credentials not found. Voice tools will be disabled.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while checking Google Cloud credentials: {e}", exc_info=True)
        return False

class Agent:
    def __init__(self, name: str = "LocalAgent", hub_url: str = None, port: int = 5001, connector: Any = None,
                 is_proactive: bool = False, execution_mode: str = "safe", batch_experience: bool = False,
                 proactive_interval: int = 600, initial_goal: str = None):
        
        self.agent_name = name
        self.hub_url = hub_url or os.environ.get("HUB_URL", "http://127.0.0.1:5000")
        self.port = port
        self.connector = connector
        self.is_proactive = is_proactive
        self.execution_mode = execution_mode
        self.batch_experience = batch_experience
        self.proactive_interval = proactive_interval
        self.initial_goal = initial_goal

        # Reconfigure logging for this specific agent instance
        log_file_path = os.path.join(os.path.dirname(__file__), "..", f"agent_{self.agent_name}_debug.log")
        # Ensure the logger is unique per agent instance to avoid duplicate handlers
        self.logger = logging.getLogger(f"agent_{self.agent_name}_logger")
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(log_file_path)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s", datefmt="[%X]")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.info(f"Logger initialized for agent {self.agent_name} logging to {log_file_path}")

        self.last_proactive_check = time.time()
        self.last_heartbeat_sent = time.time()
        self.MAX_MESSAGE_BATCH = 5 # Max messages to process per cycle
        self.experience_buffer = [] # Buffer for experiences before submitting in batch
        self.memory = Memory(agent_name=self.agent_name) # Initialize memory

        self.llm_provider_settings = self._load_llm_provider_settings() # Load settings from hub

        # Determine base model, with fallback
        self.base_model = os.environ.get("DEFAULT_LLM_MODEL", "google/gemini-pro") # Default LLM for planning if none specified

        # Initialize tools
        self.tools = self._initialize_tools()

        self.planner = Planner(
            agent_name=self.agent_name,
            base_model=self.base_model,
            memory=self.memory,
            tools=self.tools, # Pass all available tools to the planner
            llm_provider_settings=self.llm_provider_settings
        )
        self.executor = Executor(self.tools)
        self.critic = Critic(self.base_model) # Critic also needs base_model

        self.logger.info(f"Agent {self.agent_name} initialized. Proactive: {self.is_proactive}, Execution Mode: {self.execution_mode}, Batch Experience: {self.batch_experience}, Proactive Interval: {self.proactive_interval}s")


    def _initialize_tools(self) -> List[BaseTool]:
        """Initializes all available tools for the agent."""
        tools = [
            ReadFileTool(),
            WriteFileTool(),
            ListDirectoryTool(),
            RunShellCommandTool(),
            PrintTaskTool(),
            WebFetchTool(),
            SendUserMessageTool(),
            SendAgentMessageTool(),
            FinishTaskTool(),
            LLMCallTool()
        ]

        # Add conditional tools based on environment variables and credentials
        if os.environ.get("ENABLE_VOICE_TOOLS", "no").lower() == "yes" and _check_google_credentials():
            tools.extend([
                MakePhoneCallTool(),
                TranscribeVoiceTool(),
                SynthesizeSpeechTool(),
                ColdCallTool()
            ])
        else:
            self.logger.info("Voice tools not enabled or Google Cloud credentials missing.")

        if os.environ.get("ENABLE_EMAIL_TOOLS", "no").lower() == "yes":
            tools.extend([
                EmailCheckTool(),
                EmailSendTool()
            ])
        else:
            self.logger.info("Email tools not enabled.")

        if os.environ.get("ENABLE_CALENDAR_TOOLS", "no").lower() == "yes":
            tools.extend([
                CalendarCheckTool(),
                CalendarAddEventTool()
            ])
        else:
            self.logger.info("Calendar tools not enabled.")
        
        if os.environ.get("ENABLE_CONTACT_TOOLS", "no").lower() == "yes":
            tools.append(AccessContactsTool())
        else:
            self.logger.info("Contact tools not enabled.")

        if os.environ.get("ENABLE_IMAGE_TOOLS", "no").lower() == "yes":
            tools.extend([
                ImageAnalysisTool(),
                ImageGenerationTool(),
                SendImageTool()
            ])
        else:
            self.logger.info("Image tools not enabled.")

        return tools


    def _load_llm_provider_settings(self) -> Dict[str, Any]:
        """Loads LLM provider settings from the hub."""
        try:
            response = requests.get(urljoin(self.hub_url, "/api/config"))
            response.raise_for_status()
            config = response.json()
            settings = {
                "ENABLE_MOONSHOT_AI": config.get("ENABLE_MOONSHOT_AI", "no"),
                "ENABLE_OLLAMA": config.get("ENABLE_OLLAMA", "no"),
                "ENABLE_OPENROUTER": config.get("ENABLE_OPENROUTER", "no"),
                "ENABLE_VOYAGE_AI": config.get("ENABLE_VOYAGE_AI", "no"),
            }
            self.logger.debug(f"LLM Provider Settings for {self.agent_name}: {settings}")
            return settings
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error loading LLM provider settings for {self.agent_name}: {e}")
            return {}

    def send_heartbeat(self):
        try:
            response = requests.post(urljoin(self.hub_url, f"/api/heartbeat/{self.agent_name}"))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending heartbeat: {e}")

    def _process_single_message(self, message: Dict[str, Any]):
        self.logger.info(f"Agent {self.agent_name} received message: {message['content']}")
        task = message["content"]
        self.memory.add_experience(
            agent_name=self.agent_name,
            task=task,
            step={"tool": "receive_message", "args": {"message": message["content"]}},
            step_result={"status": "success", "output": "Message received."},
            reflection={"feedback": "N/A", "distilled_tips": []},
            token_usage={"provider": "none", "prompt_tokens": 0, "completion_tokens": 0} # No tokens used for receiving message
        )
        self._process_task_with_replanning(task)

    def _process_task_with_replanning(self, task: str):
        total_task_token_usage = {"moonshot_ai": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "ollama": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "openrouter": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "voyage_ai": {"prompt_tokens": 0, "completion_tokens": 0}}
        experiences = []
        plan_attempts = 0
        MAX_PLAN_ATTEMPTS = 3

        while plan_attempts < MAX_PLAN_ATTEMPTS:
            self.logger.info(f"Agent {self.agent_name} creating plan for task: {task} (Attempt {plan_attempts + 1})")
            
            plan_response = self.planner.create_plan(task, experiences) # Pass previous experiences for replanning
            current_plan = plan_response["plan"]
            
            # Aggregate token usage from planning
            for provider, usage in plan_response["token_usage"].items():
                if provider in total_task_token_usage:
                    total_task_token_usage[provider]["prompt_tokens"] += usage["prompt_tokens"]
                    total_task_token_usage[provider]["completion_tokens"] += usage["completion_tokens"]
            
            if not current_plan: # Check if plan is None or empty
                self.logger.warning(f"Agent {self.agent_name} failed to create a valid plan. Raw response: {current_plan}")
                feedback = f"Failed to create a valid plan after {plan_attempts + 1} attempts. LLM response: {plan_response.get('content', str(current_plan))}"
                reflection_response = self.planner.reflect(task, experiences + [{"status": "failed", "feedback": feedback}])
                self.memory.add_experience(self.agent_name, task, {"tool": "planner", "args": {"task": task}}, {"status": "failed", "output": feedback}, reflection_response["reflection"], reflection_response["token_usage"])
                return # Give up on this task

            step_results = []
            for step in current_plan:
                tool_name = step.get("tool")
                tool_args = step.get("args", {})
                goal = step.get("goal", "No goal specified.")
                self.logger.info(f"Agent {self.agent_name} - Step Goal: {goal}, Tool: {tool_name}, Args: {tool_args}")

                tool_output = None
                status = "success"
                message = "Tool executed successfully."
                token_usage_step = {"provider": "none", "prompt_tokens": 0, "completion_tokens": 0}

                if tool_name and tool_name != "None":
                    tool_instance = self.planner.tools.get(tool_name)
                    if tool_instance:
                        if self.execution_mode == "safe":
                            approval_status = self._request_approval(tool_name, tool_args)
                            if approval_status == "approved":
                                try:
                                    # Execute the tool and capture output
                                    tool_output = self.executor.execute(tool_name, **tool_args)
                                except Exception as e:
                                    status = "failed"
                                    message = f"Error executing tool {tool_name}: {e}"
                                    self.logger.error(message)
                            else:
                                status = "denied"
                                message = f"Tool execution for {tool_name} was denied by user."
                                self.logger.warning(message)
                        else: # unrestricted mode
                            try:
                                # Execute the tool and capture output
                                tool_output = self.executor.execute(tool_name, **tool_args)
                            except Exception as e:
                                status = "failed"
                                message = f"Error executing tool {tool_name}: {e}"
                                self.logger.error(message)
                    else:
                        status = "failed"
                        message = f"Tool '{tool_name}' not found."
                        self.logger.warning(message)
                else: # tool_name is "None" or not provided, likely a reasoning step
                    tool_output = "No tool used, reasoning step."
                    status = "success"
                    message = "Reasoning step completed."

                step_results.append({
                    "step": step,
                    "tool_output": tool_output,
                    "status": status,
                    "message": message
                })
                
                # If a tool involves an LLM call internally, its token usage would be captured there.
                # If not, token_usage_step remains default.
                # For now, we assume _call_llm in planner handles token usage.

                experience_entry = {
                    "agent_name": self.agent_name,
                    "task": task,
                    "step": step,
                    "step_result": {"status": status, "output": str(tool_output) if tool_output else message},
                    "reflection": {"feedback": "N/A", "distilled_tips": []}, # Reflection will be added later
                    "token_usage": token_usage_step # Placeholder for tool-specific token usage if applicable
                }
                experiences.append(experience_entry) # Add to current experiences for replanning/reflection

            # After all steps in a plan attempt, reflect
            self.logger.info(f"Agent {self.agent_name} reflecting on task: {task}")
            reflection_response = self.planner.reflect(task, experiences)
            reflection = reflection_response["reflection"]
            
            # Aggregate token usage from reflection
            for provider, usage in reflection_response["token_usage"].items():
                if provider in total_task_token_usage:
                    total_task_token_usage[provider]["prompt_tokens"] += usage["prompt_tokens"]
                    total_task_token_usage[provider]["completion_tokens"] += usage["completion_tokens"]

            # Store the final experiences with reflection and aggregated token usage
            for exp in experiences:
                if exp["reflection"]["feedback"] == "N/A": # Only update if not already reflected
                    exp["reflection"] = reflection
                exp["token_usage"] = total_task_token_usage # Assign aggregated token usage to all experiences from this task
                self.memory.add_experience(**exp) # Add to agent's memory
                self._submit_experience_to_hub(exp)

            # Check if task is complete, or if replanning is needed
            # For simplicity, if a plan completes without critical failure, we assume success.
            # More sophisticated logic could check reflection feedback for success criteria.
            if all(res["status"] != "failed" and res["status"] != "denied" for res in step_results):
                self.logger.info(f"Agent {self.agent_name} successfully completed task: {task}")
                return
            else:
                self.logger.warning(f"Agent {self.agent_name} encountered issues. Replanning for task: {task}")
                plan_attempts += 1
                # The 'experiences' list already contains the failed step, which will inform replanning

        self.logger.error(f"Agent {self.agent_name} failed to complete task: {task} after {MAX_PLAN_ATTEMPTS} attempts.")


    def _request_approval(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Requests user approval from the hub for a sensitive tool."""
        try:
            response = requests.post(
                urljoin(self.hub_url, "/api/request_approval"),
                json={"agent_name": self.agent_name, "tool_name": tool_name, "tool_args": tool_args}
            )
            response.raise_for_status()
            request_id = response.json().get("request_id")
            self.logger.info(f"Approval requested for {tool_name} with ID: {request_id}")

            # Poll the hub for approval status
            while True:
                time.sleep(5) # Poll every 5 seconds
                check_response = requests.get(urljoin(self.hub_url, f"/api/check_approval/{request_id}"))
                check_response.raise_for_status()
                status = check_response.json().get("status")
                if status in ["approved", "denied"]:
                    self.logger.info(f"Approval request {request_id} status: {status}")
                    return status
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error requesting or checking approval: {e}")
            return "denied" # Default to denial on error

    def _submit_experience_to_hub(self, experience: Dict[str, Any]):
        if self.batch_experience:
            self.experience_buffer.append(experience)
            self.logger.debug(f"Experience buffered for batch submission ({len(self.experience_buffer)} experiences).")
        else:
            try:
                response = requests.post(urljoin(self.hub_url, "/submit_experience"), json=[experience])
                response.raise_for_status()
                self.logger.debug("Experience submitted to hub.")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error submitting experience to hub: {e}")

    def _flush_experience_buffer(self):
        if self.experience_buffer:
            try:
                response = requests.post(urljoin(self.hub_url, "/submit_experience"), json=self.experience_buffer)
                response.raise_for_status()
                self.logger.info(f"Flushed {len(self.experience_buffer)} experiences to hub.")
                self.experience_buffer = []
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error flushing experience buffer to hub: {e}")

    def _fetch_agent_messages(self) -> List[Dict[str, Any]]:
        try:
            response = requests.get(urljoin(self.hub_url, f"/api/agent_message_queue/{self.agent_name}"))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching messages for agent {self.agent_name}: {e}")
            return []

    def run(self):
        self._register_with_hub()
        self.send_heartbeat() # Initial heartbeat

        while True:
            try:
                # Send heartbeat periodically
                if time.time() - self.last_heartbeat_sent >= 30: # Every 30 seconds
                    self.send_heartbeat()
                    self.last_heartbeat_sent = time.time()

                messages = self._fetch_agent_messages()
                if messages:
                    processed_count = 0
                    for message in messages:
                        self._process_single_message(message)
                        processed_count += 1
                        if processed_count >= self.MAX_MESSAGE_BATCH:
                            break # Process a max batch of messages per cycle
                    self._flush_experience_buffer() # Flush after processing messages

                if self.is_proactive and (time.time() - self.last_proactive_check >= self.proactive_interval):
                    self.last_proactive_check = time.time()
                    self.logger.info(f"Agent {self.agent_name} performing proactive tasks.")
                    self._distill_user_insights_from_memories()
                    self._generate_proactive_tasks_from_insights()
                    self._flush_experience_buffer() # Flush after proactive tasks

            except requests.exceptions.ConnectionError:
                self.logger.error("Connection to hub lost. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                self.logger.error(f"Agent {self.agent_name} encountered an unexpected error: {e}", exc_info=True)
                time.sleep(5) # Prevent tight loop on error

            time.sleep(1) # Short delay to prevent busy-waiting

    def _register_with_hub(self):
        try:
            response = requests.post(
                urljoin(self.hub_url, "/register_agent"),
                json={"name": self.agent_name, "url": f"http://localhost:{os.environ.get('AGENT_PORT', '5001')}"} # Agent's own URL (conceptual)
            )
            response.raise_for_status()
            self.logger.info(f"Agent {self.agent_name} successfully registered with hub.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error registering agent {self.agent_name} with hub: {e}")
            sys.exit(1) # Exit if cannot register with hub

    def _distill_user_insights_from_memories(self):
        self.logger.info(f"Agent {self.agent_name} distilling user insights from memories.")
        # Retrieve recent user messages or interactions from memory or hub
        # For now, let's simulate by pulling from hub_memory, but ideally from agent's own memory
        # Or, the planner uses the agent's memory to find relevant user messages
        
        # This part needs to be revised as agent's memory is now local.
        # The agent should query its own memory for recent user interactions.
        
        # Placeholder for actual implementation using self.memory
        recent_user_interactions = self.memory.retrieve_relevant_memories(query="recent user interactions", n_results=5)
        insights_task = "Distill key user insights and potential ongoing goals from these interactions."
        
        # Use planner to distill insights
        distill_prompt = f"""
        Given the following recent user interactions/memories:
        {json.dumps(recent_user_interactions, indent=2)}

        Analyze these and distill key user insights, underlying needs, or potential ongoing goals.
        Format your insights as a JSON array of strings, where each string is a concise insight.
        Example:
        ["User is frequently asking about project deadlines.", "User seems interested in automating report generation."]
        """
        response = self.planner.evaluate_prompt(distill_prompt)
        insights_content = response["content"]
        token_usage = response["token_usage"]

        # Add token usage to aggregated total for insights distillation
        self._aggregate_token_usage_for_agent_task(total_task_token_usage=self.memory.agent_total_token_usage, new_token_usage=token_usage)
        
        try:
            insights = json.loads(insights_content)
            if isinstance(insights, list):
                for insight in insights:
                    # Store insight in memory or submit to hub if needed
                    self.logger.info(f"Distilled Insight for {self.agent_name}: {insight}")
                    # Example: Add to memory (can be a special type of experience or directly a tip)
                    # self.memory.add_experience(self.agent_name, insights_task, {"tool": "distill_insights"}, {"status": "success", "output": insight}, {"feedback": "N/A", "distilled_tips": []}, token_usage)
            else:
                self.logger.warning(f"Distillation did not return a list: {insights_content}")
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode insights JSON: {insights_content}")
            
    def _generate_proactive_tasks_from_insights(self):
        self.logger.info(f"Agent {self.agent_name} generating proactive tasks from insights.")
        # Retrieve current distilled insights from memory
        # (This would be more sophisticated, e.g., querying for insights within a timeframe)
        
        # Placeholder for actual implementation using self.memory
        current_insights = self.memory.retrieve_relevant_memories(query="distilled user insights", n_results=3)
        if not current_insights:
            self.logger.info(f"No current insights to generate proactive tasks for {self.agent_name}.")
            return

        generate_task_prompt = f"""
        Given the following current user insights:
        {json.dumps(current_insights, indent=2)}

        Generate a list of highly relevant, actionable, and proactive tasks that the agent could undertake
        to better serve the user or address their implicit needs.
        Tasks should be concise and direct.
        Format your tasks as a JSON array of strings.
        Example:
        ["Monitor project management tool for new deadlines.", "Draft a report template for sales data."]
        """
        response = self.planner.evaluate_prompt(generate_task_prompt)
        proactive_tasks_content = response["content"]
        token_usage = response["token_usage"]

        # Add token usage to aggregated total for proactive tasks generation
        self._aggregate_token_usage_for_agent_task(total_task_token_usage=self.memory.agent_total_token_usage, new_token_usage=token_usage)

        try:
            proactive_tasks = json.loads(proactive_tasks_content)
            if isinstance(proactive_tasks, list):
                for task in proactive_tasks:
                    self.logger.info(f"Generated Proactive Task for {self.agent_name}: {task}")
                    # Process this proactive task (e.g., add to a queue or process directly)
                    self._process_task_with_replanning(task) # Directly process generated tasks
            else:
                self.logger.warning(f"Proactive task generation did not return a list: {proactive_tasks_content}")
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode proactive tasks JSON: {proactive_tasks_content}")

    def _aggregate_token_usage_for_agent_task(self, total_task_token_usage: Dict[str, Any], new_token_usage: Dict[str, Any]):
        """Helper to aggregate token usage within agent tasks."""
        provider = new_token_usage.get("provider", "none")
        if provider != "none":
            if provider not in total_task_token_usage:
                total_task_token_usage[provider] = {"prompt_tokens": 0, "completion_tokens": 0}
            total_task_token_usage[provider]["prompt_tokens"] += new_token_usage.get("prompt_tokens", 0)
            total_task_token_usage[provider]["completion_tokens"] += new_token_usage.get("completion_tokens", 0)