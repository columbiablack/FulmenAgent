import requests
import json
import os
import time
import argparse # Import argparse
from dotenv import load_dotenv

# Load environment variables from the .env file in the parent directory
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path) 

HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:5000")

def get_active_agents():
    """Fetches and prints active agents from the hub."""
    try:
        response = requests.get(f"{HUB_URL}/get_active_agents")
        response.raise_for_status()
        agents = response.json().get("agents", {})
        if agents:
            print("\n--- Active Agents ---")
            for name, url in agents.items():
                print(f"  Name: {name}, URL: {url}")
            print("---------------------\n")
            return agents
        else:
            print("No active agents found.")
            return {}
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the hub at {HUB_URL}. Is the hub running?")
        return {}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching active agents: {e}")
        return {}

def send_message_to_agent(agent_name: str, message: str):
    """Sends a message to a specific agent via the hub."""
    try:
        payload = {"agent_name": agent_name, "message": message}
        response = requests.post(f"{HUB_URL}/send_message_to_agent", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"\n--- Message Sent to {agent_name} ---")
        print(f"Status: {result.get('status')}")
        print(f"Hub Message: {result.get('message')}")
        if 'agent_response' in result:
            print(f"Agent Response: {result['agent_response'].get('response')}")
        print("----------------------------------\n")
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the hub at {HUB_URL}. Is the hub running?")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to agent '{agent_name}': {e}")
        if e.response is not None:
            print(f"Server response: {e.response.text}")
        if e.response is not None:
            print(f"Server response: {e.response.text}")

def shutdown_component(component_url: str, component_name: str):
    """Sends a shutdown request to a component."""
    try:
        response = requests.post(f"{component_url}/shutdown")
        response.raise_for_status()
        print(f"Successfully sent shutdown request to {component_name}.")
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {component_name} at {component_url}.")
    except requests.exceptions.RequestException as e:
        print(f"Error sending shutdown request to {component_name}: {e}")

def monitor_logs(log_file_path=os.path.join(os.path.dirname(__file__), "agent_debug.log")):
    """Continuously monitors and prints new lines from a log file."""
    if not os.path.exists(log_file_path):
        print(f"Error: Log file '{log_file_path}' not found. Please ensure agents are running with nohup.")
        return

    print(f"\n--- Monitoring logs from '{log_file_path}' (Press Ctrl+C to stop) ---")
    try:
        with open(log_file_path, 'r') as f:
            # Go to the end of the file
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1) # Sleep briefly
                    continue
                print(line, end='')
    except KeyboardInterrupt:
        print("\n--- Stopped monitoring logs ---")
    except Exception as e:
        print(f"An error occurred while monitoring logs: {e}")

def main():
    parser = argparse.ArgumentParser(description="Interact with the agent network.")
    parser.add_argument("--choice", type=str, help="Menu choice (1-5).")
    parser.add_argument("--agent-name", type=str, help="Name of the agent for messaging or shutdown.")
    parser.add_argument("--message", type=str, help="Message to send to an agent.")
    parser.add_argument("--component-to-shutdown", type=str, help="Name of the component to shut down ('hub' or agent name).")
    args = parser.parse_args()

    if args.choice:
        choice = args.choice
    else:
        print("Agent Interaction Menu:")
        print("1. List active agents")
        print("2. Send message to an agent")
        print("3. Exit")
        print("4. Shutdown agent or hub")
        print("5. Monitor agent logs")
        choice = input("Enter your choice: ").strip()

    if choice == '1':
        get_active_agents()
    elif choice == '2':
        agents = get_active_agents()
        if not agents:
            print("Cannot send message, no active agents.")
            return # Use return instead of continue in non-loop context
        
        if args.agent_name:
            agent_name = args.agent_name
        else:
            agent_name = input("Enter the name of the agent to message: ").strip()

        if agent_name not in agents:
            print(f"Agent '{agent_name}' not found. Please choose from the active agents listed.")
            return # Use return instead of continue
        
        if args.message:
            message = args.message
        else:
            message = input(f"Enter message for {agent_name}: ").strip()

        if message:
            send_message_to_agent(agent_name, message)
        else:
            print("Message cannot be empty.")
    elif choice == '3':
        print("Exiting interaction tool.")
        return # Use return instead of break
    elif choice == '4':
        if args.component_to_shutdown:
            component_to_shutdown = args.component_to_shutdown
        else:
            component_to_shutdown = input("Enter the name of the agent (e.g., 'Agent1') or 'hub' to shut down: ").strip()

        if component_to_shutdown.lower() == 'hub':
            shutdown_component(HUB_URL, "Hub")
        else:
            agents = get_active_agents()
            if component_to_shutdown in agents:
                agent_url = agents[component_to_shutdown]
                shutdown_component(agent_url, f"Agent '{component_to_shutdown}'")
            else:
                print(f"Component '{component_to_shutdown}' not found. Please enter a valid agent name or 'hub'.")
    elif choice == '5':
        monitor_logs()
    else:
        print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()

