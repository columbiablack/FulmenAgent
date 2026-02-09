import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import logging
from agent_network.src.planner import Planner

# Configure logging for the script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def list_openrouter_models_cli():
    """
    CLI function to list available OpenRouter models, with an option to show only free ones.
    """
    planner = Planner()

    if not planner.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY environment variable is not set.")
        logger.info("Please set your OpenRouter API key to list models. Example: export OPENROUTER_API_KEY='sk-...'")
        return

    logger.info("Fetching all available models from OpenRouter...")
    all_models = planner.get_available_models(free_only=False)
    
    if not all_models:
        logger.warning("No models found or an error occurred while fetching models.")
        return

    logger.info("\n--- All Available OpenRouter Models ---")
    for model in all_models:
        logger.info(f"ID: {model['id']}, Name: {model['name']}, Free: {model['is_free']}")

    logger.info("\n--- Free OpenRouter Models ---")
    free_models = [model for model in all_models if model['is_free']]
    if free_models:
        for model in free_models:
            logger.info(f"ID: {model['id']}, Name: {model['name']}")
        logger.info("\nTo use a specific model, set the OPENROUTER_MODEL environment variable. Example: export OPENROUTER_MODEL='nvidia/nemotron-3-nano-30b-a3b:free'")
    else:
        logger.info("No free models found.")

if __name__ == "__main__":
    list_openrouter_models_cli()
