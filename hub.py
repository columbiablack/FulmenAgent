print("HUB.PY IS EXECUTING!")
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for
import threading
from rich.logging import RichHandler
import os
from waitress import serve
import json # ADD json for pretty printing
import signal # ADD signal for process termination
import uuid # NEW: For unique approval request IDs
import time # Ensure time is imported
from dotenv import load_dotenv, set_key # Import load_dotenv and set_key

# Configure logging for the hub
log_file_path = os.path.join(os.path.dirname(__file__), "agent_debug.log")
logging.basicConfig(
    level="DEBUG", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(), logging.FileHandler(log_file_path)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.cache = {}

hub_memory = {
    "experiences": [],
    "distilled_tips": [],
    "active_agents": {},
    "agent_message_queues": {},
    "recent_experiences": [],
    "MAX_RECENT_EXPERIENCES": 20,
    "user_messages": [],
    "pending_approvals": {}, # NEW: For handling approvals
    "total_token_usage": { # NEW: To track aggregated token usage
        "moonshot_ai": {"prompt_tokens": 0, "completion_tokens": 0},
        "ollama": {"prompt_tokens": 0, "completion_tokens": 0},
        "openrouter": {"prompt_tokens": 0, "completion_tokens": 0},
        "voyage_ai": {"prompt_tokens": 0, "completion_tokens": 0}
    }
}

launched_agent_processes = {}

shutdown_event = threading.Event()

waitress_server = None

# -------------------- Routes --------------------

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    # Convert timestamps to human-readable format for display
    display_agents = {}
    for name, details in hub_memory["active_agents"].items():
        display_agents[name] = {
            "url": details["url"],
            "last_heartbeat": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(details["last_heartbeat"]))
        }

    return render_template("dashboard.html", 
                           active_agents=display_agents, # Use display_agents for dashboard
                           user_messages=hub_memory["user_messages"],
                           distilled_tips=hub_memory["distilled_tips"],
                           recent_experiences=hub_memory["recent_experiences"],
                           pending_approvals=hub_memory["pending_approvals"])

@app.route("/register_agent", methods=["POST"])
def register_agent():
    data = request.json
    agent_name = data.get("name")
    agent_url = data.get("url")
    if agent_name and agent_url:
        hub_memory["active_agents"][agent_name] = {"url": agent_url, "last_heartbeat": time.time()}
        hub_memory["agent_message_queues"][agent_name] = [] # Initialize message queue for new agent
        logger.info(f"Agent '{agent_name}' registered with URL: {agent_url}")
        return jsonify({"status": "success", "message": f"Agent {agent_name} registered."}), 200
    return jsonify({"status": "error", "message": "Invalid agent registration data."}), 400

@app.route("/api/heartbeat/<agent_name>", methods=["POST"])
def agent_heartbeat(agent_name):
    if agent_name in hub_memory["active_agents"]:
        hub_memory["active_agents"][agent_name]["last_heartbeat"] = time.time()
        logger.debug(f"Received heartbeat from agent '{agent_name}'.")
        return jsonify({"status": "success", "message": f"Heartbeat received for {agent_name}."}), 200
    return jsonify({"status": "error", "message": f"Agent {agent_name} not found."}), 404

@app.route("/get_active_agents", methods=["GET"])
def get_active_agents():
    # Optionally, clean up inactive agents here based on last_heartbeat
    return jsonify(hub_memory["active_agents"]), 200

@app.route("/submit_experience", methods=["POST"])
def submit_experience():
    experiences = request.json
    for exp in experiences:
        hub_memory["experiences"].append(exp)
        hub_memory["recent_experiences"].append(exp)
        if len(hub_memory["recent_experiences"]) > hub_memory["MAX_RECENT_EXPERIENCES"]:
            hub_memory["recent_experiences"].pop(0) # Keep only the most recent experiences

        # Aggregate token usage if present in the experience
        if "token_usage" in exp and exp["token_usage"]["provider"] != "none":
            provider = exp["token_usage"]["provider"]
            prompt_tokens = exp["token_usage"]["prompt_tokens"]
            completion_tokens = exp["token_usage"]["completion_tokens"]

            if provider in hub_memory["total_token_usage"]:
                hub_memory["total_token_usage"][provider]["prompt_tokens"] += prompt_tokens
                hub_memory["total_token_usage"][provider]["completion_tokens"] += completion_tokens
            else:
                # Initialize provider if it's new (e.g., for future extensions)
                hub_memory["total_token_usage"][provider] = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
            logger.debug(f"Aggregated token usage for {provider}: Prompt={prompt_tokens}, Completion={completion_tokens}")

    logger.debug(f"Received {len(experiences)} experiences.")
    return jsonify({"status": "success", "message": "Experiences submitted."}), 200

@app.route("/shutdown_agent/<agent_name>", methods=["POST"])
def shutdown_agent(agent_name):
    if agent_name in hub_memory["active_agents"]:
        agent_url = hub_memory["active_agents"][agent_name]["url"] # Get the agent's URL
        
        # Deregister from hub's memory
        del hub_memory["active_agents"][agent_name]
        if agent_name in hub_memory["agent_message_queues"]:
            del hub_memory["agent_message_queues"][agent_name]
        logger.info(f"Agent '{agent_name}' deregistered from hub.")

        # Send shutdown request to the agent's Flask server
        try:
            requests.post(f"{agent_url}/shutdown", timeout=5)
            logger.info(f"Sent shutdown signal to agent '{agent_name}' at {agent_url}.")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to send shutdown signal to agent '{agent_name}' at {agent_url}: {e}")

        # Terminate the agent process if it was launched by this hub
        if agent_name in launched_agent_processes:
            pid = launched_agent_processes.pop(agent_name)
            try:
                os.killpg(pid, signal.SIGTERM) # Use SIGTERM for graceful shutdown
                logger.info(f"Terminated agent process group for '{agent_name}' (PID: {pid}).")
            except ProcessLookupError:
                logger.warning(f"Agent process for '{agent_name}' (PID: {pid}) not found, already terminated.")
            except Exception as e:
                logger.error(f"Error terminating agent process group for '{agent_name}' (PID: {pid}): {e}")

        return jsonify({"status": "success", "message": f"Agent {agent_name} deregistered and shutdown signal sent."}), 200
    return jsonify({"status": "error", "message": f"Agent {agent_name} not found."}), 404

# NEW: Dashboard API endpoints
@app.route("/api/agents")
def api_agents():
    return jsonify(hub_memory["active_agents"])

@app.route("/api/experiences")
def api_experiences():
    return jsonify(hub_memory["recent_experiences"]) # Return recent experiences for dashboard

@app.route("/api/user_messages", methods=["GET", "POST"])
def api_user_messages():
    if request.method == "POST":
        data = request.json
        message = data.get("message")
        agent_name = data.get("agent_name")
        if message and agent_name and agent_name in hub_memory["agent_message_queues"]:
            hub_memory["agent_message_queues"][agent_name].append({"sender": "user", "message": message})
            logger.info(f"User message for agent '{agent_name}' queued.")
            return jsonify({"status": "success", "message": "Message queued for processing."}), 200
        return jsonify({"status": "error", "message": "Invalid message or agent_name."}), 400
    else: # GET
        return jsonify(hub_memory["user_messages"]) # Return messages from agents to user

@app.route("/api/agent_message_queue/<agent_name>", methods=["GET"])
def api_agent_message_queue(agent_name):
    if agent_name in hub_memory["agent_message_queues"]:
        messages = hub_memory["agent_message_queues"][agent_name]
        hub_memory["agent_message_queues"][agent_name] = [] # Clear queue after retrieval
        return jsonify(messages), 200
    return jsonify({"status": "error", "message": f"Agent {agent_name} not found or no message queue."}), 404

# NEW: Approval API endpoints
@app.route("/api/request_approval", methods=["POST"])
def request_approval():
    data = request.json
    agent_name = data.get("agent_name")
    tool_name = data.get("tool_name")
    tool_args = data.get("tool_args")

    if not all([agent_name, tool_name, tool_args]):
        return jsonify({"status": "error", "message": "Missing required data for approval request."}), 400
    
    request_id = str(uuid.uuid4())
    hub_memory["pending_approvals"][request_id] = {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "status": "pending", # pending, approved, denied
        "timestamp": time.time()
    }
    logger.info(f"Approval request '{request_id}' from agent '{agent_name}' for tool '{tool_name}' logged.")
    return jsonify({"status": "success", "request_id": request_id}), 200

@app.route("/api/approvals", methods=["GET"])
def get_approvals():
    return jsonify(hub_memory["pending_approvals"]), 200

@app.route("/api/token_usage", methods=["GET"])
def get_token_usage():
    return jsonify(hub_memory["total_token_usage"]), 200

@app.route("/api/approve/<request_id>", methods=["POST"])
def approve_request(request_id):
    if request_id not in hub_memory["pending_approvals"]:
        return jsonify({"status": "error", "message": "Request ID not found."}), 404

    decision = request.json.get("decision") # "approved" or "denied"
    if decision not in ["approved", "denied"]:
        return jsonify({"status": "error", "message": "Invalid decision. Must be 'approved' or 'denied'."}), 400
    
    hub_memory["pending_approvals"][request_id]["status"] = decision
    logger.info(f"Approval request '{request_id}' has been '{decision}'.")
    return jsonify({"status": "success", "message": f"Request {request_id} has been {decision}."}), 200

@app.route("/api/check_approval/<request_id>", methods=["GET"])
def check_approval(request_id):
    if request_id not in hub_memory["pending_approvals"]:
        return jsonify({"status": "error", "message": "Request ID not found."}), 404
    
    approval_status = hub_memory["pending_approvals"][request_id]["status"]
    if approval_status in ["approved", "denied"]:
        # Once an agent has checked the final status, we can remove it from the list
        # to prevent it from growing indefinitely.
        del hub_memory["pending_approvals"][request_id]
        logger.info(f"Agent checked final status of request '{request_id}'. Removing from pending list.")
    
    return jsonify({"status": approval_status}), 200

# NEW: Configuration API endpoints
DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.exists(DOTENV_PATH):
    # If .env is not in the current directory, try one level up (project root)
    DOTENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')

@app.route("/api/config", methods=["GET"])
def api_get_config():
    load_dotenv(DOTENV_PATH) # Reload to get latest values

    # List of all config keys that should be read from environment
    all_keys = [
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OLLAMA_BASE_URL", "OLLAMA_MODEL",
        "MOONSHOT_API_KEY", "MOONSHOT_MODEL", "DISCORDAGENT_DISCORD_TOKEN",
        "DISCORDAGENT_DISCORD_CHANNEL_ID", "TELEGRAMAGENT_TELEGRAM_TOKEN",
        "TELEGRAMAGENT_TELEGRAM_ALLOWED_CHATS", "LINEAGENT_LINE_CHANNEL_SECRET",
        "LINEAGENT_LINE_CHANNEL_ACCESS_TOKEN", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN", "X_CONSUMER_KEY",
        "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
        "ENABLE_MOONSHOT_AI", "ENABLE_OLLAMA", "ENABLE_OPENROUTER", "VOYAGE_AI_API_KEY",
        "ENABLE_VOYAGE_AI", "EMAIL_API_SERVICE", "EMAIL_API_AUTH_METHOD",
        "CALENDAR_API_SERVICE", "CALENDAR_API_AUTH_METHOD", "DEFAULT_PROACTIVE_LOOPS",
        "DEFAULT_EXECUTION_MODE", "DEFAULT_BATCH_EXPERIENCE", "DEFAULT_PROACTIVE_INTERVAL"
    ]
    
    # List of keys that are sensitive and should be masked
    sensitive_keys = [
        "OPENROUTER_API_KEY", "MOONSHOT_API_KEY", "DISCORDAGENT_DISCORD_TOKEN",
        "TELEGRAMAGENT_TELEGRAM_TOKEN", "LINEAGENT_LINE_CHANNEL_SECRET",
        "LINEAGENT_LINE_CHANNEL_ACCESS_TOKEN", "TWILIO_AUTH_TOKEN",
        "WHATSAPP_ACCESS_TOKEN", "X_CONSUMER_KEY", "X_CONSUMER_SECRET",
        "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "VOYAGE_AI_API_KEY"
    ]

    config = {key: os.environ.get(key, "") for key in all_keys}

    # Mask sensitive keys for security
    # If a key exists, send an empty string to the frontend for display
    for key in sensitive_keys:
        logger.debug(f"[DEBUG api_get_config] Before masking - Key: {key}, Value: '{config[key]}'")
        if config[key]:
            config[key] = "" # Mask by sending empty string
            logger.debug(f"[DEBUG api_get_config] After masking - Key: {key}, Value: '{config[key]}'")
    return jsonify(config), 200

@app.route("/api/config", methods=["POST"])
def api_set_config():
    from dotenv import set_key
    
    # Reload .env at the start to get the absolute latest environment variables
    load_dotenv(DOTENV_PATH) 

    data = request.json
    
    # Helper to safely update sensitive keys, preventing empty values from overwriting real ones
    def update_sensitive_key(key_name, incoming_value):
        current_value_in_env = os.environ.get(key_name, "")
        logger.debug(f"[DEBUG api_set_config] Key: {key_name}")
        logger.debug(f"[DEBUG api_set_config] Incoming value: '{incoming_value}'")
        logger.debug(f"[DEBUG api_set_config] Current value in env (pre-load_dotenv): '{current_value_in_env}'")
        if incoming_value == "" and current_value_in_env:
            logger.info(f"[DEBUG api_set_config] {key_name} received as empty value. Retaining existing key in .env.")
        else:
            logger.debug(f"[DEBUG api_set_config] Setting {key_name} to '{incoming_value}'.")
            set_key(DOTENV_PATH, key_name, incoming_value)

    # Process all keys from the form
    sensitive_keys = [
        "OPENROUTER_API_KEY", "MOONSHOT_API_KEY", "DISCORDAGENT_DISCORD_TOKEN",
        "TELEGRAMAGENT_TELEGRAM_TOKEN", "LINEAGENT_LINE_CHANNEL_SECRET",
        "LINEAGENT_LINE_CHANNEL_ACCESS_TOKEN", "TWILIO_AUTH_TOKEN",
        "WHATSAPP_ACCESS_TOKEN", "X_CONSUMER_KEY", "X_CONSUMER_SECRET",
        "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "VOYAGE_AI_API_KEY"
    ]
    
    checkbox_keys = ["ENABLE_MOONSHOT_AI", "ENABLE_OLLAMA", "ENABLE_OPENROUTER", "ENABLE_VOYAGE_AI"]

    for key, value in data.items():
        if key in sensitive_keys:
            update_sensitive_key(key, value)
        elif key in checkbox_keys:
            logger.debug(f"[DEBUG api_set_config] Checkbox {key} is checked. Setting to 'yes'.")
            set_key(DOTENV_PATH, key, "yes") # If key is present, it's checked
        else:
            logger.debug(f"[DEBUG api_set_config] Setting non-sensitive key {key} to '{value}'.")
            set_key(DOTENV_PATH, key, value)
    
    # Handle unchecked checkboxes
    for key in checkbox_keys:
        if key not in data:
            logger.debug(f"[DEBUG api_set_config] Checkbox {key} is unchecked. Setting to 'no'.")
            set_key(DOTENV_PATH, key, "no")

    # After modifying .env, reload all environment variables into os.environ for the current process
    load_dotenv(DOTENV_PATH, override=True)

    logger.info("Configuration updated via dashboard API.")
    return jsonify({"status": "success", "message": "Configuration updated."}), 200

@app.route("/receive_user_message", methods=["POST"])
def receive_user_message():
    data = request.json
    agent_name = data.get("agent_name")
    message = data.get("message")
    title = data.get("title")
    if agent_name and message:
        hub_memory["user_messages"].append({
            "agent_name": agent_name,
            "message": message,
            "title": title,
            "timestamp": time.time()
        })
        logger.info(f"Received message from agent '{agent_name}' for user.")
        return jsonify({"status": "success", "message": "Message queued for processing."}), 200
    return jsonify({"status": "error", "message": "Invalid message data."}), 400

@app.route("/shutdown", methods=["POST"])
def shutdown_hub():
    logger.info("Hub shutdown requested.")
    # Use a separate thread to shut down the server to allow the response to be sent
    threading.Thread(target=initiate_shutdown).start()
    return jsonify({"status": "success", "message": "Hub is shutting down."}), 200

def initiate_shutdown():
    global waitress_server
    if waitress_server:
        logger.info("Attempting to stop Waitress server...")
        waitress_server.shutdown() # This is the graceful way to stop Waitress
        logger.info("Waitress server stopped.")
    # Terminate all launched agent processes
    for agent_name, pid in list(launched_agent_processes.items()): # Iterate over a copy
        try:
            os.killpg(pid, signal.SIGTERM) # Use SIGTERM
            logger.info(f"Terminated agent process group for '{agent_name}' (PID: {pid}) during hub shutdown.")
        except ProcessLookupError:
            logger.warning(f"Agent process for '{agent_name}' (PID: {pid}) not found during hub shutdown, already terminated.")
        except Exception as e:
            logger.error(f"Error terminating agent process group for '{agent_name}' (PID: {pid}) during hub shutdown: {e}")
    launched_agent_processes.clear() # Clear the dictionary after attempting to kill all

    shutdown_event.set() # Signal main thread to exit
    os._exit(0) # Force exit if waitress.shutdown() isn't enough (e.g. if not run with serve)


# Ensure time is imported for last_heartbeat
import time
import sys
import os
import subprocess # Make sure subprocess is imported

# Ensure time is imported for last_heartbeat
# import time -- already at the top of the file

@app.route("/launch_agent", methods=["POST"])
def launch_agent():
    data = request.json
    agent_name = data.get("agent_name")
    connector_type = data.get("connector_type")
    is_proactive = data.get("is_proactive", False)
    initial_goal = data.get("initial_goal", "")
    execution_mode = data.get("execution_mode", "unrestricted") # Default to unrestricted for autonomous operation
    batch_experience = data.get("batch_experience", False)
    proactive_interval = data.get("proactive_interval", 600)

    if not agent_name:
        return jsonify({"status": "error", "message": "Agent name is required."}), 400

    # Construct the command to run main_agent_entrypoint.py
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "main_agent_entrypoint.py"),
        "--num-agents", "1",
        "--agent-names", agent_name,
        "--connector-types", connector_type,
        "--proactive-loops", "yes" if is_proactive else "no",
        "--execution-modes", execution_mode,
        "--batch-experience", "yes" if batch_experience else "no",
        "--proactive-interval", str(proactive_interval)
    ]
    if initial_goal:
        cmd.extend(["--initial-goal", initial_goal])

    try:
        # Launch the agent process
        # Using preexec_fn=os.setsid to detach the child process from the parent
        # so it continues to run even if the hub process is restarted.
        # Redirect stdout/stderr to files for debugging.
        agent_stdout_path = os.path.join(os.path.dirname(__file__), f"agent_{agent_name}_stdout.log")
        agent_stderr_path = os.path.join(os.path.dirname(__file__), f"agent_{agent_name}_stderr.log")

        # Explicitly set PYTHONPATH for the subprocess
        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = project_root

        with open(agent_stdout_path, "w") as stdout_file, open(agent_stderr_path, "w") as stderr_file:
            # Explicitly redirect stdin to /dev/null to ensure non-interactivity
            with open(os.devnull, 'r') as devnull:
                process = subprocess.Popen(cmd, stdin=devnull, stdout=stdout_file, stderr=stderr_file, preexec_fn=os.setsid, env=env)
                launched_agent_processes[agent_name] = process.pid # Store the PID
        
        logger.info(f"Launched agent '{agent_name}' with command: {' '.join(cmd)}")
        return jsonify({"status": "success", "message": f"Agent '{agent_name}' launched successfully!"}), 200
    except Exception as e:
        logger.error(f"Error launching agent '{agent_name}': {e}")
        return jsonify({"status": "error", "message": f"Failed to launch agent: {e}"}), 500


if __name__ == "__main__":
    logger.info(f"Hub server starting on http://0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000)