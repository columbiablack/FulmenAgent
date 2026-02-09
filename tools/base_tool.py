from abc import ABC, abstractmethod

class BaseTool(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def run(self, **kwargs):
        """
        Executes the tool's functionality.
        All arguments should be passed as keyword arguments.
        """
        pass

    def __str__(self):
        return f"Tool: {self.name} - {self.description}"
