import os
import asyncio
import threading
import uuid
from agent_network.connectors.base_connector import BaseConnector

# Try to import LINE Bot SDK components
try:
    from linebot import LineBotApi, WebhookHandler
    from linebot.exceptions import InvalidSignatureError
    from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage
except ImportError:
    raise ImportError("The 'line-bot-sdk' library is not installed. Please install it with 'pip install line-bot-sdk'.")

class LineConnector(BaseConnector):
    def __init__(self, agent, logger, channel_secret, channel_access_token):
        super().__init__(agent, logger)
        if not channel_secret or not channel_access_token:
            raise ValueError("LINE channel secret and access token are required for the LINE connector.")
        self.channel_secret = channel_secret
        self.channel_access_token = channel_access_token
        self.line_bot_api = LineBotApi(channel_access_token)
        self.handler = WebhookHandler(channel_secret)
        self.webhook_thread = None
        self.webhook_running = False

        # Register message handler with the WebhookHandler
        @self.handler.add(MessageEvent, message=TextMessage)
        def handle_text_message(event):
            self._handle_line_message(event, event.message.text, "text")

        @self.handler.add(MessageEvent, message=ImageMessage)
        def handle_image_message(event):
            self._handle_line_message(event, event.message.id, "image") # Message ID to download image later

    def start(self):
        # LINE connector runs as a webhook, so its "start" means it's ready to receive webhook calls.
        # The actual Flask endpoint for the webhook will be handled by the Hub or main_agent_entrypoint.
        self.logger.info("LINE connector initialized. Awaiting webhook events.")
        # We don't need a separate thread for polling as it's webhook driven.
        # The webhook handling will occur in the Flask context of the Hub.

    def stop(self):
        self.logger.info("LINE connector stopped.")

    def handle_webhook_event(self, body, signature):
        """
        This method is called by the external Flask webhook endpoint to process LINE events.
        """
        try:
            self.handler.handle(body, signature)
        except InvalidSignatureError:
            self.logger.error("Invalid LINE signature. Please check your channel secret.")
            return "Invalid signature", 400
        except Exception as e:
            self.logger.error(f"Error handling LINE webhook event: {e}", exc_info=True)
            return "Internal server error", 500
        return "OK", 200

    def _handle_line_message(self, event: MessageEvent, message_content: str, message_type: str):
        user_id = event.source.user_id
        reply_token = event.reply_token
        
        # Create a unique session ID for this conversation
        # LINE messages typically have a userId, groupId, or roomId.
        # For simplicity, we'll use userId for now, but could be extended to group/room IDs.
        session_id = f"line_{user_id}"

        image_path = None
        if message_type == "image":
            try:
                message_content = event.message.id # In case of image, message_content is the message ID
                message_content = "Image received." # Text to send to agent
                image_content = self.line_bot_api.get_message_content(event.message.id)
                temp_dir = "temp_attachments"
                os.makedirs(temp_dir, exist_ok=True)
                
                filename = f"{temp_dir}/{uuid.uuid4()}.jpg" # Assuming JPEG for now
                with open(filename, 'wb') as f:
                    for chunk in image_content.iter_content():
                        f.write(chunk)
                image_path = filename
                self.logger.info(f"Downloaded LINE image: {image_path}")
            except Exception as e:
                self.logger.error(f"Failed to download LINE image: {e}")
                image_path = None

        line_context = {
            "connector": self,
            "user_id": user_id,
            "reply_token": reply_token,
            "session_id": session_id,
            "message_type": message_type # text, image, etc.
        }
        self.logger.info(f"Received LINE message from {user_id} (Session: {session_id}): {message_content}")
        self.agent.handle_message(message_content, line_context, image_path=image_path)

    async def send_response(self, response_text, context):
        reply_token = context.get("reply_token")
        user_id = context.get("user_id")
        if reply_token:
            try:
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text=response_text))
                self.logger.info(f"Replied to LINE user {user_id} (via reply token).")
            except Exception as e:
                self.logger.error(f"Failed to reply to LINE user {user_id}: {e}")
        elif user_id: # Fallback to push message if reply token is not available (e.g., proactive messages)
            try:
                self.line_bot_api.push_message(user_id, TextSendMessage(text=response_text))
                self.logger.info(f"Pushed message to LINE user {user_id}.")
            except Exception as e:
                self.logger.error(f"Failed to push message to LINE user {user_id}: {e}")

    async def send_image(self, image_path, context):
        reply_token = context.get("reply_token")
        user_id = context.get("user_id")
        if not image_path:
            self.logger.warning("No image path provided for LINE send_image.")
            return
        
        # LINE requires image URLs for ImageSendMessage, not local paths.
        # This means we need a way to host the image and get a URL.
        # For simplicity, I'll log a warning and not send the image directly.
        # A real implementation would involve uploading the image to a publicly accessible server.
        self.logger.error("LINE Messaging API requires publicly accessible image URLs for ImageSendMessage. Local paths are not supported.")
        self.logger.info("Skipping image send for LINE. Agent should be aware of this limitation or use a tool to upload images.")

        # If a reply token is available, you might send a text message indicating image sending failed
        if reply_token:
            try:
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text="[Image sending failed: LINE requires image URLs]"))
            except Exception as e:
                self.logger.error(f"Failed to send error message to LINE user {user_id}: {e}")
        elif user_id:
            try:
                self.line_bot_api.push_message(user_id, TextSendMessage(text="[Image sending failed: LINE requires image URLs]"))
            except Exception as e:
                self.logger.error(f"Failed to send error message to LINE user {user_id}: {e}")