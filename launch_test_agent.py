
import requests
import json
import os

HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:5000")

def launch_test_agent():
    print(f"Attempting to launch agent via hub at {HUB_URL}...")
    launch_data = {
        "agent_name": "TestAgent",
        "connector_type": "none",
        "is_proactive": False,
        "initial_goal": "Respond to user messages.",
        "execution_mode": "safe",
        "batch_experience": False,
        "proactive_interval": 600
    }
    try:
        response = requests.post(f"{HUB_URL}/launch_agent", json=launch_data)
        response.raise_for_status()
        print(f"Response from hub: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error launching agent: {e}")
        if e.response:
            print(f"Hub response: {e.response.text}")

if __name__ == "__main__":
    launch_test_agent()
