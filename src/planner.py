from typing import List, Dict, Any
from src.memory import Memory
import os
import json
import logging
import requests # Re-add requests
import time # Re-add time
import random # Re-add random
from ollama import Client # Re-add Ollama Client
from openai import OpenAI # Re-add OpenAI for OpenRouter/Moonshot

class Planner:
    def __init__(self, agent_name: str, base_model: Any, memory: Memory, tools: List[Any], llm_provider_settings: Dict[str, Any]):
        self.agent_name = agent_name
        self.base_model = base_model
        self.memory = memory
        self.tools = {tool.name: tool for tool in tools}
        self.llm_provider_settings = llm_provider_settings
        self.logger = logging.getLogger(f"Planner.{agent_name}")

        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        self.openrouter_chat_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions") # Use base_url from env or default
        self.openrouter_models_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") + "/models"
        self.free_models = [] # To store a list of available free OpenRouter models
        self.blacklisted_models = set() # To store OpenRouter models that hit daily rate limits

        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL")
        self.ollama_model = os.environ.get("OLLAMA_MODEL") # Specific Ollama model chosen by user
        self.ollama_client = None
        self.available_ollama_models = [] # To store a list of available Ollama models

        self.moonshot_api_key = os.environ.get("MOONSHOT_API_KEY")
        self.moonshot_model = os.environ.get("MOONSHOT_MODEL") # Specific Kimi model chosen by user
        self.moonshot_client = None # Placeholder for Moonshot OpenAI client
        self.available_moonshot_models = [] # To store a list of available Kimi models (not actively fetched but for consistency)

        # Log initial LLM provider status
        self.logger.info(f"DEBUG: Planner initialized. "
                         f"OPENROUTER_API_KEY: {'SET' if self.openrouter_api_key else 'NOT SET'}. "
                         f"OLLAMA_BASE_URL: {'SET' if self.ollama_base_url else 'NOT SET'}. "
                         f"MOONSHOT_API_KEY: {'SET' if self.moonshot_api_key else 'NOT SET'}. "
                         f"ENABLE_MOONSHOT_AI: {self.llm_provider_settings.get('ENABLE_MOONSHOT_AI')}. "
                         f"ENABLE_OLLAMA: {self.llm_provider_settings.get('ENABLE_OLLAMA')}. "
                         f"ENABLE_OPENROUTER: {self.llm_provider_settings.get('ENABLE_OPENROUTER')}.")

        # Initialize OpenRouter models if enabled
        if self.llm_provider_settings.get("ENABLE_OPENROUTER") == "yes" and self.openrouter_api_key:
            self.free_models = self._get_available_openrouter_models(free_only=True)
            if not self.free_models:
                self.logger.warning("No free OpenRouter models found. Planner might rely on other providers.")
            else:
                self.logger.info(f"Found {len(self.free_models)} free OpenRouter models.")
        elif self.llm_provider_settings.get("ENABLE_OPENROUTER") == "yes" and not self.openrouter_api_key:
             self.logger.warning("OPENROUTER_API_KEY not set, OpenRouter will not be used.")

        # Initialize Ollama client and models if enabled
        if self.llm_provider_settings.get("ENABLE_OLLAMA") == "yes" and self.ollama_base_url:
            try:
                self.ollama_client = Client(host=self.ollama_base_url)
                self.available_ollama_models = self._get_available_ollama_models()
                if not self.available_ollama_models:
                    self.logger.warning(f"No models found on Ollama server at {self.ollama_base_url}.")
                    self.ollama_client = None # Disable Ollama if no models
                else:
                    self.logger.info(f"Found {len(self.available_ollama_models)} models on Ollama server at {self.ollama_base_url}.")
                    if not self.ollama_model and self.available_ollama_models:
                        # If no specific Ollama model is chosen, default to the first one available
                        self.ollama_model = self.available_ollama_models[0]['name']
                        self.logger.info(f"No specific OLLAMA_MODEL set. Defaulting to first available: {self.ollama_model}")
            except Exception as e:
                self.logger.error(f"Error initializing Ollama client at {self.ollama_base_url}: {e}")
                self.ollama_client = None
        elif self.llm_provider_settings.get("ENABLE_OLLAMA") == "yes" and not self.ollama_base_url:
            self.logger.warning("OLLAMA_BASE_URL not set, Ollama will not be used.")

        # Initialize Moonshot client if enabled
        if self.llm_provider_settings.get("ENABLE_MOONSHOT_AI") == "yes" and self.moonshot_api_key:
            self.moonshot_client = OpenAI(
                api_key=self.moonshot_api_key,
                base_url=os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
            )
        elif self.llm_provider_settings.get("ENABLE_MOONSHOT_AI") == "yes" and not self.moonshot_api_key:
            self.logger.warning("MOONSHOT_API_KEY not set, Moonshot AI will not be used.")

    def _get_available_openrouter_models(self, free_only: bool = True) -> List[str]:
        headers = {"Authorization": f"Bearer {self.openrouter_api_key}"}
        try:
            response = requests.get(self.openrouter_models_url, headers=headers)
            response.raise_for_status()
            models = response.json().get('data', [])
            available_models = [
                m['id'] for m in models
                if (not free_only or m.get('pricing', {}).get('prompt', 0) == 0) and m['id'] not in self.blacklisted_models
            ]
            return available_models
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching OpenRouter models: {e}")
            return []

    def _get_available_ollama_models(self) -> List[Dict[str, Any]]:
        if not self.ollama_client:
            return []
        try:
            response = self.ollama_client.list()
            return response.get('models', [])
        except Exception as e:
            self.logger.error(f"Error fetching Ollama models: {e}")
            return []

    def _call_llm(self, prompt: str, temperature: float = 0.7, provider: str = "openrouter", model: str = None) -> Dict[str, Any]:
        """
        Calls the appropriate LLM based on the provider settings.
        Returns the content of the LLM's response and a dictionary of token usage.
        """
        token_usage = {"provider": provider, "prompt_tokens": 0, "completion_tokens": 0}
        
        try:
            if provider == "openrouter" and self.llm_provider_settings.get("ENABLE_OPENROUTER") == "yes" and self.openrouter_api_key:
                # Ensure the OpenAI client is initialized correctly with base_url and api_key from self.
                client = OpenAI(
                    base_url=self.openrouter_chat_url.replace("/chat/completions", ""), # Extract base URL from chat_url
                    api_key=self.openrouter_api_key
                )
                used_model = model if model else (os.environ.get("OPENROUTER_MODEL") or self.base_model) # Use agent's base_model as ultimate fallback
                if not used_model:
                    self.logger.warning(f"No OpenRouter model specified for _call_llm.")
                    return {"content": "Error: No OpenRouter model specified.", "token_usage": token_usage}

                chat_completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=used_model,
                    temperature=temperature,
                    stream=False
                )
                if chat_completion.usage:
                    token_usage["prompt_tokens"] = chat_completion.usage.prompt_tokens
                    token_usage["completion_tokens"] = chat_completion.usage.completion_tokens
                return {"content": chat_completion.choices[0].message.content, "token_usage": token_usage}

            elif provider == "ollama" and self.llm_provider_settings.get("ENABLE_OLLAMA") == "yes" and self.ollama_client:
                used_model = model if model else (self.ollama_model or self.base_model) # Use agent's base_model as ultimate fallback
                if not used_model:
                    self.logger.warning(f"No Ollama model specified for _call_llm.")
                    return {"content": "Error: No Ollama model specified.", "token_usage": token_usage}

                response = self.ollama_client.chat( # Use self.ollama_client
                    model=used_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": temperature}
                )
                # Ollama's API response doesn't directly provide token usage like OpenAI's.
                # You might need to estimate or implement a tokenizer if precise tracking is needed.
                # For now, we'll return 0 tokens for Ollama.
                return {"content": response["message"]["content"], "token_usage": token_usage}

            elif provider == "moonshot" and self.llm_provider_settings.get("ENABLE_MOONSHOT_AI") == "yes" and self.moonshot_client:
                used_model = model if model else (self.moonshot_model or self.base_model) # Use agent's base_model as ultimate fallback
                if not used_model:
                    self.logger.warning(f"No Moonshot AI model specified for _call_llm.")
                    return {"content": "Error: No Moonshot AI model specified.", "token_usage": token_usage}

                chat_completion = self.moonshot_client.chat.completions.create( # Use self.moonshot_client
                    messages=[{"role": "user", "content": prompt}],
                    model=used_model,
                    temperature=temperature,
                    stream=False
                )
                if chat_completion.usage:
                    token_usage["prompt_tokens"] = chat_completion.usage.prompt_tokens
                    token_usage["completion_tokens"] = chat_completion.usage.completion_tokens
                return {"content": chat_completion.choices[0].message.content, "token_usage": token_usage}
            
            else:
                self.logger.warning(f"LLM provider '{provider}' is either not enabled, not configured, or not supported.")
                return {"content": f"Error: LLM provider '{provider}' is not enabled, not configured, or not supported.", "token_usage": token_usage}

        except Exception as e:
            self.logger.error(f"Error calling LLM with provider '{provider}': {e}")
            return {"content": f"Error calling LLM: {e}", "token_usage": token_usage}

    def evaluate_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Evaluates a prompt using the LLM and returns the response content and token usage.
        """
        # Default to OpenRouter if enabled, otherwise try Ollama, then Moonshot
        provider = "openrouter"
        if self.llm_provider_settings.get("ENABLE_OPENROUTER") != "yes":
            if self.llm_provider_settings.get("ENABLE_OLLAMA") == "yes":
                provider = "ollama"
            elif self.llm_provider_settings.get("ENABLE_MOONSHOT_AI") == "yes":
                provider = "moonshot"
            else:
                self.logger.warning("No LLM provider is enabled for evaluation.")
                return {"content": "No LLM provider enabled.", "token_usage": {"provider": "none", "prompt_tokens": 0, "completion_tokens": 0}}
        
        response = self._call_llm(prompt, temperature=0.5, provider=provider)
        return response # Returns {"content": ..., "token_usage": {...}}

    def create_plan(self, task: str, recent_experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Creates a plan to address the given task, incorporating recent experiences and relevant memories.
        Returns the plan (as a string) and aggregated token usage.
        """
        aggregated_token_usage = {"moonshot_ai": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "ollama": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "openrouter": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "voyage_ai": {"prompt_tokens": 0, "completion_tokens": 0}}

        relevant_memories = []
        if self.llm_provider_settings.get("ENABLE_VOYAGE_AI") == "yes":
            try:
                # Retrieve relevant memories using Voyage AI embeddings
                self.logger.info(f"Retrieving relevant memories for task: {task}")
                retrieved_docs = self.memory.retrieve_relevant_memories(query=task, n_results=5)
                for doc in retrieved_docs:
                    relevant_memories.append(doc)
                
                # Token usage for embedding model is handled internally by Memory, 
                # but for planning LLM call, we still track.
            except Exception as e:
                self.logger.error(f"Error retrieving relevant memories with Voyage AI: {e}")
                relevant_memories = ["Error retrieving memories."]
        else:
            self.logger.info("Voyage AI is not enabled for memory retrieval.")

        memories_str = "\n".join(relevant_memories) if relevant_memories else "No relevant memories found."
        
        prompt = f"""
        You are an AI agent designed to create a plan to accomplish a given task.
        You have access to the following tools: {list(self.tools.keys())}.
        
        Here is the task you need to accomplish:
        TASK: {task}
        
        Here are some relevant memories from your past experiences:
        {memories_str}
        
        Based on the task and your memories, outline a detailed plan. 
        The plan should consist of a series of steps. For each step, clearly state:
        1. The goal of the step.
        2. The tool you intend to use (from the provided list).
        3. The arguments for the tool.
        
        Your response should be a JSON object with a single key "plan", 
        which is a list of step objects. Each step object should have "goal", "tool", and "args" keys.
        Example:
        {{
            "plan": [
                {{"goal": "Understand the user's request", "tool": "None", "args": {{"query": "user request"}}}},
                {{"goal": "Search for relevant information", "tool": "search_tool", "args": {{"query": "AI agent best practices"}}}},
                {{"goal": "Synthesize information and formulate response", "tool": "None", "args": {{"information": "search results"}}}},
            ]
        }}
        If no tools are directly applicable, use "None" for the tool and provide reasoning in the goal.
        """
        
        response = self._call_llm(prompt, temperature=0.7)
        plan_content = response["content"]
        
        # Aggregate token usage from the planning LLM call
        if response["token_usage"]["provider"] != "none":
            provider = response["token_usage"]["provider"]
            if provider in aggregated_token_usage:
                aggregated_token_usage[provider]["prompt_tokens"] += response["token_usage"]["prompt_tokens"]
                aggregated_token_usage[provider]["completion_tokens"] += response["token_usage"]["completion_tokens"]
            else: # Should not happen if `aggregated_token_usage` is pre-populated
                aggregated_token_usage[provider] = response["token_usage"]

        try:
            plan = json.loads(plan_content)
            return {"plan": plan["plan"], "token_usage": aggregated_token_usage}
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode plan JSON: {plan_content}")
            return {"plan": [{"goal": f"Error: Could not parse plan from LLM. Raw response: {plan_content}", "tool": "None", "args": {}}], "token_usage": aggregated_token_usage}

    def reflect(self, task: str, experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reflects on the task and experiences to generate feedback and distilled tips.
        Returns reflection (as a string) and aggregated token usage.
        """
        aggregated_token_usage = {"moonshot_ai": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "ollama": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "openrouter": {"prompt_tokens": 0, "completion_tokens": 0},
                                  "voyage_ai": {"prompt_tokens": 0, "completion_tokens": 0}}
        
        experiences_str = "\n".join([json.dumps(exp) for exp in experiences])
        
        prompt = f"""
        You are an AI agent designed to reflect on your performance after attempting a task.
        Here is the original task: {task}
        Here are the experiences (steps taken and their results):
        {experiences_str}
        
        Based on these, provide constructive feedback on your performance and distill any valuable tips or lessons learned.
        Your response should be a JSON object with two keys: "feedback" (a string) and "distilled_tips" (a list of strings).
        Example:
        {{
            "feedback": "The initial search was too broad...",
            "distilled_tips": ["Always refine search queries...", "Consider edge cases..."]
        }}
        """
        response = self._call_llm(prompt, temperature=0.7)
        reflection_content = response["content"]

        # Aggregate token usage from the reflection LLM call
        if response["token_usage"]["provider"] != "none":
            provider = response["token_usage"]["provider"]
            if provider in aggregated_token_usage:
                aggregated_token_usage[provider]["prompt_tokens"] += response["token_usage"]["prompt_tokens"]
                aggregated_token_usage[provider]["completion_tokens"] += response["token_usage"]["completion_tokens"]
            else: # Should not happen if `aggregated_token_usage` is pre-populated
                aggregated_token_usage[provider] = response["token_usage"]

        try:
            reflection = json.loads(reflection_content)
            return {"reflection": reflection, "token_usage": aggregated_token_usage}
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode reflection JSON: {reflection_content}")
            return {"reflection": {"feedback": f"Error: Could not parse reflection from LLM. Raw response: {reflection_content}", "distilled_tips": []}, "token_usage": aggregated_token_usage}
