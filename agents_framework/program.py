# Enhanced agent framework
import logging
from dataclasses import dataclass
from typing import List, Optional

logging.basicConfig(level=logging.INFO)

@dataclass
class Task:
    description: str
    priority: int = 0

class Agent:
    def __init__(self, name: str):
        self.name = name
        self.tasks: List[Task] = []

    def assign_task(self, task: Task):
        self.tasks.append(task)
        logging.info(f"{self.name} assigned task: {task.description}")

    def complete_task(self) -> Optional[Task]:
        if self.tasks:
            task = self.tasks.pop(0)
            logging.info(f"{self.name} completed task: {task.description}")
            return task
        return None

    def status(self):
        pending = len(self.tasks)
        logging.info(f"{self.name} has {pending} pending task(s)")

def main():
    agents = {
        "Alpha": Agent("Alpha"),
        "Beta": Agent("Beta"),
        "Gamma": Agent("Gamma")
    }

    tasks = [
        Task("monitor_environment", priority=1),
        Task("process_data", priority=2),
        Task("communicate_results", priority=3)
    ]

    for task in sorted(tasks, key=lambda t: t.priority):
        agent = list(agents.values())[len(agents) % len(agents)]
        agent.assign_task(task)

    for name, agent in agents.items():
        completed = agent.complete_task()
        if completed:
            print(f"{name} completed: {completed.description}")
        else:
            print(f"{name} has no tasks")

    for name, agent in agents.items():
        agent.status()

if __name__ == "__main__":
    main()
