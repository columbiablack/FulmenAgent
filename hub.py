print("HUB.PY IS EXECUTING!")
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for
import threading
from rich.logging import RichHandler
import os
from waitress import serve
import json # ADD json for pretty printing
import signal # ADD signal for process termination
import sys # For sys.executable in subprocess calls
import atexit # For cleanup on hub exit
import uuid # NEW: For unique approval request IDs
import time # Ensure time is imported
from dotenv import load_dotenv, set_key # Import load_dotenv and set_key
import zipfile # NEW: For handling zip file uploads
import shutil # NEW: For directory operations (e.g., rmtree)
from werkzeug.utils import secure_filename # NEW: For securing uploaded filenames
from pathlib import Path # NEW: For path manipulation
import requests # IMPORTED: Add requests for HTTP communication

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
    },
    "global_plugin_preferences": {}, # NEW: To store global enable/disable status for plugins
    "global_auto_install_deps": True, # NEW: Global setting for auto-installing plugin dependencies
    "discovered_plugins": {} # NEW: To store details of all plugins found in the plugins directory
}

launched_agent_processes = {}

shutdown_event = threading.Event()

waitress_server = None

def _cleanup_agent_processes():
    """Kill all launched agent processes on hub exit (Ctrl+C, SIGTERM, etc.)."""
    for agent_name, pid in list(launched_agent_processes.items()):
        try:
            os.killpg(pid, signal.SIGTERM)
            logger.info(f"Cleanup: Terminated agent '{agent_name}' (PID: {pid})")
        except ProcessLookupError:
            pass  # Already dead
        except Exception as e:
            logger.error(f"Cleanup: Error killing agent '{agent_name}' (PID: {pid}): {e}")
    launched_agent_processes.clear()

atexit.register(_cleanup_agent_processes)

def _signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM to ensure agent cleanup before exit."""
    logger.info(f"Received signal {signum}, cleaning up agent processes...")
    _cleanup_agent_processes()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

def _discover_all_plugins():
    """
    Scans the plugins directory for all available plugins and stores their manifest data.
    """
    logger.info("Starting plugin discovery...")
    plugins_dir = Path(__file__).parent / "plugins"
    if not plugins_dir.is_dir():
        logger.info(f"Plugins directory not found at {plugins_dir}. No plugins will be discovered.")
        return

    logger.info(f"Discovering all plugins in {plugins_dir}...")
    for plugin_path in plugins_dir.iterdir():
        if plugin_path.is_dir():
            manifest_path = plugin_path / "manifest.json"
            if manifest_path.is_file():
                try:
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)
                    plugin_name = manifest.get('name', plugin_path.name)
                    hub_memory["discovered_plugins"][plugin_name] = {
                        "name": plugin_name,
                        "description": manifest.get("description", "No description provided."),
                        "version": manifest.get("version", "N/A"),
                        "author": manifest.get("author", "Unknown"),
                        "path": str(plugin_path),
                        "status": hub_memory["global_plugin_preferences"].get(plugin_name, "enabled") # Reflect global preference
                    }
                    logger.info(f"Discovered plugin: {plugin_name}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid manifest.json in plugin '{plugin_path.name}'. Skipping discovery.")
                except Exception as e:
                    logger.error(f"Error discovering plugin '{plugin_path.name}': {e}", exc_info=True)
    logger.info(f"Finished plugin discovery. Found {len(hub_memory['discovered_plugins'])} plugins.")

# Initial plugin discovery when the hub starts
_discover_all_plugins()

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
                           pending_approvals=hub_memory["pending_approvals"],
                           discovered_plugins=hub_memory["discovered_plugins"])

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
        data = request.json
        hub_memory["active_agents"][agent_name]["last_heartbeat"] = time.time()
        
        # NEW: Store plugin data from heartbeat
        plugins_data = data.get("plugins")
        if plugins_data:
            hub_memory["active_agents"][agent_name]["plugins"] = plugins_data
            # Initialize global plugin preferences for newly seen plugins
            for plugin_name, manifest in plugins_data.get("manifests", {}).items():
                if plugin_name not in hub_memory["global_plugin_preferences"]:
                    hub_memory["global_plugin_preferences"][plugin_name] = "enabled" # Default to enabled
                    logger.info(f"Discovered new plugin '{plugin_name}'. Defaulting to 'enabled'.")
        
        # NEW: Store Ollama models from heartbeat
        ollama_models = data.get("ollama_models")
        if ollama_models:
            hub_memory["active_agents"][agent_name]["ollama_models"] = ollama_models
            logger.debug(f"Received Ollama models for agent '{agent_name}': {ollama_models}")

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
        if "token_usage" in exp and exp["token_usage"]:
            token_data = exp["token_usage"]
            # Handle flat format: {"provider": "ollama", "prompt_tokens": 10, ...}
            if "provider" in token_data and token_data["provider"] != "none":
                provider = token_data["provider"]
                prompt_tokens = token_data.get("prompt_tokens", 0)
                completion_tokens = token_data.get("completion_tokens", 0)
                if provider not in hub_memory["total_token_usage"]:
                    hub_memory["total_token_usage"][provider] = {"prompt_tokens": 0, "completion_tokens": 0}
                hub_memory["total_token_usage"][provider]["prompt_tokens"] += prompt_tokens
                hub_memory["total_token_usage"][provider]["completion_tokens"] += completion_tokens
                logger.debug(f"Aggregated token usage for {provider}: Prompt={prompt_tokens}, Completion={completion_tokens}")
            else:
                # Handle nested format: {"ollama": {"prompt_tokens": 10, ...}, "openrouter": {...}}
                for provider, usage in token_data.items():
                    if isinstance(usage, dict) and (usage.get("prompt_tokens", 0) > 0 or usage.get("completion_tokens", 0) > 0):
                        if provider not in hub_memory["total_token_usage"]:
                            hub_memory["total_token_usage"][provider] = {"prompt_tokens": 0, "completion_tokens": 0}
                        hub_memory["total_token_usage"][provider]["prompt_tokens"] += usage.get("prompt_tokens", 0)
                        hub_memory["total_token_usage"][provider]["completion_tokens"] += usage.get("completion_tokens", 0)
                        logger.debug(f"Aggregated token usage for {provider}: Prompt={usage.get('prompt_tokens', 0)}, Completion={usage.get('completion_tokens', 0)}")

    logger.debug(f"Received {len(experiences)} experiences.")
    return jsonify({"status": "success", "message": "Experiences submitted."}), 200

@app.route("/shutdown_agent/<agent_name>", methods=["POST"])
def shutdown_agent(agent_name):
    if agent_name in hub_memory["active_agents"]:
        agent_url = hub_memory["active_agents"][agent_name]["url"] # Get the agent's URL
        
        # Terminate the agent process if it was launched by this hub
        process_terminated_successfully = False
        if agent_name in launched_agent_processes:
            pid = launched_agent_processes.pop(agent_name)
            try:
                os.killpg(pid, signal.SIGTERM) # Use SIGTERM for graceful shutdown
                logger.info(f"Terminated agent process group for '{agent_name}' (PID: {pid}).")
                process_terminated_successfully = True
            except ProcessLookupError:
                logger.warning(f"Agent process for '{agent_name}' (PID: {pid}) not found, already terminated.")
                process_terminated_successfully = True # Consider it terminated if not found
            except Exception as e:
                logger.error(f"Error terminating agent process group for '{agent_name}' (PID: {pid}): {e}")
        
        # Deregister from hub's memory only if process termination was attempted (and possibly succeeded)
        # This prevents 404 errors if the process lingers but hub thinks it's gone
        if agent_name in hub_memory["active_agents"]:
            del hub_memory["active_agents"][agent_name]
        if agent_name in hub_memory["agent_message_queues"]:
            del hub_memory["agent_message_queues"][agent_name]
        logger.info(f"Agent '{agent_name}' deregistered from hub's memory.")

        status_message = f"Agent {agent_name} deregistered from hub."
        if process_terminated_successfully:
            status_message += " Process termination attempted and likely successful."
        else:
            status_message += " Process termination failed or was not applicable."


        return jsonify({"status": "success", "message": status_message}), 200
    return jsonify({"status": "error", "message": f"Agent {agent_name} not found."}), 404

# NEW: Dashboard API endpoints
@app.route("/api/agents")
def api_agents():
    return jsonify(hub_memory["active_agents"])

@app.route("/api/plugins", methods=["GET"])
def api_plugins():
    # Return all discovered plugins, along with their global status
    discovered_plugins_list = []
    for plugin_name, details in hub_memory["discovered_plugins"].items():
        plugin_status = hub_memory["global_plugin_preferences"].get(plugin_name, "enabled")
        details["status"] = plugin_status # Update status based on global preference
        discovered_plugins_list.append(details)
    return jsonify(discovered_plugins_list), 200

@app.route("/api/plugins/toggle/<plugin_name>", methods=["POST"])
def api_toggle_plugin(plugin_name):
    action = request.json.get("action") # "enable" or "disable"
    if action not in ["enable", "disable"]:
        return jsonify({"status": "error", "message": "Invalid action. Must be 'enable' or 'disable'."}), 400

    if plugin_name not in hub_memory["global_plugin_preferences"] and action == "disable":
        # If a plugin isn't explicitly listed, it means it's implicitly enabled.
        # So we can set its status to disabled if requested.
        hub_memory["global_plugin_preferences"][plugin_name] = "disabled"
        logger.info(f"Plugin '{plugin_name}' explicitly set to 'disabled'.")
        return jsonify({"status": "success", "message": f"Plugin '{plugin_name}' disabled. Agent restart required."}), 200
    elif plugin_name in hub_memory["global_plugin_preferences"]:
        hub_memory["global_plugin_preferences"][plugin_name] = action + "d" # "enabled" or "disabled"
        logger.info(f"Plugin '{plugin_name}' set to '{action}d'.")
        return jsonify({"status": "success", "message": f"Plugin '{plugin_name}' {action}d. Agent restart required."}), 200
    
    return jsonify({"status": "error", "message": f"Plugin '{plugin_name}' not found or no change."}), 404

@app.route("/api/agent/<agent_name>/plugin_status/<plugin_name>", methods=["GET"])
def api_agent_plugin_status(agent_name, plugin_name):
    # Agents query this to know if they should load a plugin
    status = hub_memory["global_plugin_preferences"].get(plugin_name, "enabled") # Default to enabled
    return jsonify({"status": status}), 200

# NEW: Plugin Upload Endpoint
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'temp_plugin_uploads')
ALLOWED_EXTENSIONS = {'zip'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/plugins/upload", methods=["POST"])
def api_upload_plugin():
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    if 'plugin_zip' not in request.files:
        return jsonify({"status": "error", "message": "No file part in the request."}), 400
    file = request.files['plugin_zip']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file."}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        logger.info(f"Received plugin upload: {filename}")

        try:
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                # Get the name of the top-level folder inside the zip
                namelist = zip_ref.namelist()
                if not namelist:
                    raise ValueError("Zip file is empty.")

                # Determine target directory name (e.g., from zip filename or manifest)
                plugin_base_name = os.path.splitext(filename)[0]
                extract_to_path = Path(__file__).parent / "plugins" / plugin_base_name

                # Zip-slip protection: validate all paths before extraction
                for member in namelist:
                    member_path = (extract_to_path / member).resolve()
                    if not str(member_path).startswith(str(extract_to_path.resolve())):
                        raise ValueError(f"Zip contains path traversal entry: {member}")

                # Check for existing plugin with the same name
                if extract_to_path.exists():
                    shutil.rmtree(extract_to_path) # Overwrite existing plugin if present
                    logger.warning(f"Existing plugin directory '{plugin_base_name}' overwritten.")

                os.makedirs(extract_to_path, exist_ok=True)
                zip_ref.extractall(extract_to_path)
            
            # Basic validation: check for manifest.json
            if not (extract_to_path / "manifest.json").is_file():
                shutil.rmtree(extract_to_path) # Clean up if invalid structure
                raise ValueError("Uploaded plugin is missing manifest.json.")

            logger.info(f"Plugin '{plugin_base_name}' extracted to {extract_to_path}. Agent restart required.")
            return jsonify({"status": "success", "message": f"Plugin '{plugin_base_name}' uploaded and extracted successfully. Restart your agents to activate."}), 200

        except zipfile.BadZipFile:
            logger.error(f"Uploaded file '{filename}' is not a valid zip file.")
            return jsonify({"status": "error", "message": "Uploaded file is not a valid zip file."}), 400
        except ValueError as ve:
            logger.error(f"Plugin validation failed: {ve}")
            return jsonify({"status": "error", "message": f"Plugin validation failed: {ve}"}), 400
        except Exception as e:
            logger.error(f"Error processing plugin upload: {e}")
            return jsonify({"status": "error", "message": f"Error processing plugin upload: {e}"}), 500
        finally:
            # Clean up the temporary zip file
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        return jsonify({"status": "error", "message": "Invalid file type. Only .zip files are allowed."}), 400

@app.route("/api/plugins/remove/<plugin_name>", methods=["POST"])
def api_remove_plugin(plugin_name):
    plugin_path = Path(__file__).parent / "plugins" / plugin_name
    if not plugin_path.is_dir():
        return jsonify({"status": "error", "message": f"Plugin '{plugin_name}' not found."}), 404
    
    try:
        shutil.rmtree(plugin_path)
        if plugin_name in hub_memory["global_plugin_preferences"]:
            del hub_memory["global_plugin_preferences"][plugin_name] # Remove preference entry
        logger.info(f"Plugin '{plugin_name}' removed successfully from {plugin_path}.")
        return jsonify({"status": "success", "message": f"Plugin '{plugin_name}' removed. Restart your agents to fully unregister its tools."}), 200
    except Exception as e:
        logger.error(f"Error removing plugin '{plugin_name}': {e}")
        return jsonify({"status": "error", "message": f"Failed to remove plugin '{plugin_name}': {e}"}), 500

@app.route("/api/experiences")
def api_experiences():
    return jsonify(hub_memory["recent_experiences"]) # Return recent experiences for dashboard

@app.route("/api/user_messages", methods=["GET", "POST"])
def api_user_messages():
    if request.method == "POST":
        data = request.json
        message = data.get("message")
        agent_name = data.get("agent_name")
        if message and agent_name:
            if agent_name not in hub_memory["agent_message_queues"]:
                hub_memory["agent_message_queues"][agent_name] = [] # Initialize if not exists
                logger.info(f"Created message queue for new agent '{agent_name}'.")
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
        "TWILIO_PHONE_NUMBER", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN",
        "X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
        "EXA_API_KEY",
        "ENABLE_MOONSHOT_AI", "ENABLE_OLLAMA", "ENABLE_OPENROUTER", "VOYAGE_AI_API_KEY",
        "ENABLE_VOYAGE_AI", "ENABLE_VOICE_TOOLS", "EMAIL_API_SERVICE", "EMAIL_API_AUTH_METHOD",
        "CALENDAR_API_SERVICE", "CALENDAR_API_AUTH_METHOD", "DEFAULT_PROACTIVE_LOOPS",
        "DEFAULT_EXECUTION_MODE", "DEFAULT_BATCH_EXPERIENCE", "DEFAULT_PROACTIVE_INTERVAL"
    ]
    
    # List of keys that are sensitive and should be masked
    sensitive_keys = [
        "OPENROUTER_API_KEY", "MOONSHOT_API_KEY", "DISCORDAGENT_DISCORD_TOKEN",
        "TELEGRAMAGENT_TELEGRAM_TOKEN", "LINEAGENT_LINE_CHANNEL_SECRET",
        "LINEAGENT_LINE_CHANNEL_ACCESS_TOKEN", "TWILIO_AUTH_TOKEN",
        "WHATSAPP_ACCESS_TOKEN", "X_CONSUMER_KEY", "X_CONSUMER_SECRET",
        "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "VOYAGE_AI_API_KEY",
        "EXA_API_KEY"
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
        "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "VOYAGE_AI_API_KEY",
        "EXA_API_KEY"
    ]
    
    checkbox_keys = ["ENABLE_MOONSHOT_AI", "ENABLE_OLLAMA", "ENABLE_OPENROUTER", "ENABLE_VOYAGE_AI", "ENABLE_VOICE_TOOLS"]

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

# NEW: API endpoint for auto-install dependencies preference
@app.route("/api/settings/auto_install_deps", methods=["GET", "POST"])
def api_auto_install_deps_setting():
    if request.method == "GET":
        return jsonify({"status": hub_memory["global_auto_install_deps"]}), 200
    elif request.method == "POST":
        data = request.json
        enable = data.get("enable")
        if isinstance(enable, bool):
            hub_memory["global_auto_install_deps"] = enable
            logger.info(f"Global auto-install dependencies set to: {enable}")
            return jsonify({"status": "success", "message": f"Auto-install dependencies set to {enable}."}), 200
        return jsonify({"status": "error", "message": "Invalid 'enable' value. Must be boolean."}), 400

# Cache for OpenRouter models list
_openrouter_models_cache = {"data": None, "timestamp": 0}
OPENROUTER_CACHE_TTL = 600  # 10 minutes

@app.route("/api/openrouter/models", methods=["GET"])
def api_openrouter_models():
    """Fetch available models from OpenRouter API with free/paid info."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"status": "error", "message": "OPENROUTER_API_KEY not configured."}), 400

    include_paid = request.args.get("include_paid", "false").lower() == "true"

    # Check cache
    now = time.time()
    if _openrouter_models_cache["data"] and (now - _openrouter_models_cache["timestamp"]) < OPENROUTER_CACHE_TTL:
        all_models = _openrouter_models_cache["data"]
    else:
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=15)
            resp.raise_for_status()
            raw_models = resp.json().get("data", [])

            all_models = []
            for m in raw_models:
                prompt_price = m.get("pricing", {}).get("prompt", "0")
                is_free = str(prompt_price) == "0"
                all_models.append({
                    "id": m.get("id", ""),
                    "name": m.get("name", m.get("id", "")),
                    "free": is_free,
                    "context_length": m.get("context_length", 0),
                })
            # Sort: free first, then alphabetically
            all_models.sort(key=lambda x: (not x["free"], x["name"].lower()))

            _openrouter_models_cache["data"] = all_models
            _openrouter_models_cache["timestamp"] = now
            logger.info(f"Fetched {len(all_models)} models from OpenRouter ({sum(1 for m in all_models if m['free'])} free).")
        except Exception as e:
            logger.error(f"Error fetching OpenRouter models: {e}")
            return jsonify({"status": "error", "message": f"Failed to fetch models: {e}"}), 500

    if include_paid:
        filtered = all_models
    else:
        filtered = [m for m in all_models if m["free"]]

    return jsonify({"status": "success", "models": filtered}), 200

@app.route("/send_message_to_agent_by_name", methods=["POST"])
def send_message_to_agent_by_name():
    data = request.json
    target_agent_name = data.get("target_agent_name")
    message = data.get("message")
    sender_agent_name = data.get("sender_agent_name")
    if target_agent_name and message:
        if target_agent_name not in hub_memory["agent_message_queues"]:
            hub_memory["agent_message_queues"][target_agent_name] = []
        hub_memory["agent_message_queues"][target_agent_name].append({
            "sender": sender_agent_name or "unknown_agent",
            "message": message
        })
        logger.info(f"Message from agent '{sender_agent_name}' queued for agent '{target_agent_name}'.")
        return jsonify({"status": "success", "message": f"Message queued for agent '{target_agent_name}'."}), 200
    return jsonify({"status": "error", "message": "Invalid target_agent_name or message."}), 400

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


@app.route("/api/reset", methods=["POST"])
def reset_hub():
    """Reset the hub: kill all agents and clear all in-memory state."""
    logger.info("Hub reset requested.")

    # Kill all launched agent processes
    killed = 0
    for agent_name, pid in list(launched_agent_processes.items()):
        try:
            os.killpg(pid, signal.SIGTERM)
            logger.info(f"Reset: Terminated agent '{agent_name}' (PID: {pid})")
            killed += 1
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Reset: Error killing agent '{agent_name}' (PID: {pid}): {e}")
    launched_agent_processes.clear()

    # Clear all in-memory state (preserve constants and config)
    hub_memory["experiences"] = []
    hub_memory["distilled_tips"] = []
    hub_memory["active_agents"] = {}
    hub_memory["agent_message_queues"] = {}
    hub_memory["recent_experiences"] = []
    hub_memory["user_messages"] = []
    hub_memory["pending_approvals"] = {}
    hub_memory["total_token_usage"] = {
        "moonshot_ai": {"prompt_tokens": 0, "completion_tokens": 0},
        "ollama": {"prompt_tokens": 0, "completion_tokens": 0},
        "openrouter": {"prompt_tokens": 0, "completion_tokens": 0},
        "voyage_ai": {"prompt_tokens": 0, "completion_tokens": 0}
    }
    # Keep global_plugin_preferences, global_auto_install_deps, discovered_plugins

    logger.info(f"Hub reset complete. Killed {killed} agents, cleared all memory.")
    return jsonify({"status": "success", "message": f"Hub reset. Killed {killed} agent(s), cleared all data."}), 200

import subprocess

@app.route("/launch_agent", methods=["POST"])
def launch_agent():
    data = request.json
    agent_name = data.get("agent_name")
    connector_type = data.get("connector_type")
    is_proactive = data.get("is_proactive", False)
    initial_goal = data.get("initial_goal", None)
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
    if initial_goal is not None:
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
