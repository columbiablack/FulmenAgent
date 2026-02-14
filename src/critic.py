from typing import Dict, Any
import json
from agent_network.src.planner import Planner
from agent_network.src.memory import Memory
import logging

logger = logging.getLogger(__name__)

class Critic:
    def __init__(self, planner: Planner, memory: Memory):
        self.planner = planner
        self.memory = memory

    def evaluate(self, task: str, step_result: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Critic: Evaluating step result using LLM.")

        # Construct a prompt for the LLM to get feedback
        prompt = f"""
        You are the Critic for an AI agent. Your role is to evaluate the outcome of a single step
        performed by the agent to accomplish a task. Provide constructive feedback.

        Task: {task}
        Step Result: {json.dumps(step_result, indent=2)}

        Based on the above, provide:
        1. An overall evaluation (e.g., "success", "failure", "neutral").
        2. Detailed constructive feedback.

        Your response MUST be a JSON object with two keys: "evaluation" and "feedback".
        Example:
        {{
            "evaluation": "success",
            "feedback": "The file was read successfully, and its content is relevant to the task."
        }}
        """

        try:
            llm_response = self.planner.evaluate_prompt(prompt)
            # evaluate_prompt returns {"content": str, "token_usage": dict}
            llm_response_str = llm_response["content"]
            llm_evaluation = json.loads(llm_response_str.strip())

            evaluation = llm_evaluation.get("evaluation", "neutral")
            feedback = llm_evaluation.get("feedback", "No specific feedback from LLM.")

            logger.info(f"Critic LLM Evaluation: {evaluation}, Feedback: {feedback}")
            return {
                "task": task,
                "step_result": step_result,
                "evaluation": evaluation,
                "feedback": feedback
            }

        except json.JSONDecodeError as e:
            logger.error(f"Critic: Failed to decode LLM response for evaluation as JSON: {e}. Response: {llm_response_str}")
            return {
                "task": task,
                "step_result": step_result,
                "evaluation": "neutral",
                "feedback": f"LLM evaluation failed (JSON decode error: {e}). Original response: {llm_response_str}"
            }
        except Exception as e:
            logger.error(f"Critic: An error occurred during LLM evaluation: {e}", exc_info=True)
            return {
                "task": task,
                "step_result": step_result,
                "evaluation": "neutral",
                "feedback": f"LLM evaluation failed ({e})."
            }
