from abc import ABC, abstractmethod

class BaseConnector(ABC):
    """
    Abstract base class for all connectors.
    A connector is responsible for bridging communication between a user on a specific platform (like Discord, Telegram, etc.) and an agent.
    """

    def __init__(self, agent, logger):
        self.agent = agent
        self.logger = logger

    @abstractmethod
    def start(self):
        """
        Starts the connector. This method should run in a non-blocking way,
        typically by starting a new thread.
        """
        pass

    @abstractmethod
    def stop(self):
        """
        Stops the connector gracefully.
        """
        pass

    @abstractmethod
    async def send_response(self, response_text, context):
        """
        Sends a response back to the platform from which the original message came.

        Args:
            response_text (str): The text of the message to send.
            context (dict): A dictionary containing platform-specific information
                            needed to send the response (e.g., channel_id for Discord).
        """
        pass

    @abstractmethod
    async def send_image(self, image_path, context):
        """
        Sends an image file back to the platform from which the original message came.

        Args:
            image_path (str): The path to the image file to send.
            context (dict): A dictionary containing platform-specific information
                            needed to send the image (e.g., channel_id for Discord).
        """
        pass
