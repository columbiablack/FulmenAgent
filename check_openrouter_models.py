import os
import sys


# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_network.src.planner import Planner
from dotenv import load_dotenv

# Load environment variables from .env file in the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

planner = Planner()
free_models = planner.get_available_models(free_only=True)

multimodal_models = []
for model in free_models:
    # Simple heuristic to find multimodal models
    if "vision" in model["id"].lower() or "image" in model["id"].lower() or "multimodal" in model["id"].lower():
        multimodal_models.append(model)

if multimodal_models:
    print("Found the following free multimodal models on OpenRouter:")
    for model in multimodal_models:
        print(f"- ID: {model['id']}, Name: {model['name']}")
else:
    print("No free multimodal models found on OpenRouter that explicitly mention 'vision', 'image', or 'multimodal'.")

print("\nAll free models found on OpenRouter:")
for model in free_models:
    print(f"- ID: {model['id']}, Name: {model['name']}")
