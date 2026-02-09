import threading
import asyncio
import os
import uuid
from agent_network.connectors.base_connector import BaseConnector

# We need to check if the telegram library is installed
try:
    from telegram import Update
    from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
except ImportError:
    raise ImportError("The 'python-telegram-bot' library is not installed. Please install it with 'pip install python-telegram-bot'.")


class TelegramConnector(BaseConnector):
    def __init__(self, agent, logger, token, allowed_chat_ids):
        super().__init__(agent, logger)
        if not token:
            raise ValueError("Telegram token is required for the Telegram connector.")
        self.token = token
        self.allowed_chat_ids = [int(chat_id) for chat_id in allowed_chat_ids] if allowed_chat_ids else []
        self.updater = Updater(token)
        
        # Register handlers
        # Filters.text & ~Filters.command will handle text messages
        # Filters.photo will handle photo messages
        self.updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command | Filters.photo, self._handle_message))

    def start(self):
        self.thread = threading.Thread(target=self.updater.start_polling, daemon=True)
        self.thread.start()
        self.logger.info("Telegram connector started in a background thread.")

    def stop(self):
        self.logger.info("Stopping Telegram connector...")
        self.updater.stop()
        self.logger.info("Telegram connector stopped.")

    def _handle_message(self, update: Update, context: CallbackContext):
        chat_id = update.message.chat_id
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            self.logger.warning(f"Received message from unauthorized Telegram chat ID: {chat_id}")
            update.message.reply_text("You are not authorized to use this bot.")
            return
            
        message_text = update.message.text if update.message.text else ""
        image_path = None
        message_thread_id = update.message.message_thread_id # NEW: Get thread ID

        if update.message.photo:
            self.logger.info(f"Received photo from Telegram chat {chat_id}, thread {message_thread_id}")
            try:
                # Get the largest photo size
                photo_file = update.message.photo[-1].get_file()
                
                temp_dir = "temp_attachments"
                os.makedirs(temp_dir, exist_ok=True)
                
                filename = f"{temp_dir}/{uuid.uuid4()}_{photo_file.file_path.split('/')[-1]}"
                photo_file.download(filename)
                image_path = filename
                self.logger.info(f"Downloaded Telegram photo: {image_path}")
            except Exception as e:
                self.logger.error(f"Failed to download Telegram photo: {e}")

        self.logger.info(f"Received message from Telegram user {update.message.from_user.name} in chat {chat_id}, thread {message_thread_id}: {message_text}")
        
        # The context is passed so the agent knows where and how to respond
        session_id = f"tg_{chat_id}_{message_thread_id}" if message_thread_id else f"tg_{chat_id}"
        tg_context = {
            "connector": self, 
            "chat_id": chat_id, 
            "message_thread_id": message_thread_id,
            "author": update.message.from_user.name,
            "session_id": session_id
        }
        
        # Pass the message and image path to the agent to handle
        self.agent.handle_message(message_text, tg_context, image_path=image_path)

    async def send_response(self, response_text, context):
        chat_id = context.get("chat_id")
        message_thread_id = context.get("message_thread_id") # NEW: Get thread ID
        if chat_id:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    self.updater.bot.send_message,
                    chat_id,
                    response_text,
                    message_thread_id=message_thread_id
                )
            except Exception as e:
                self.logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")

    async def send_image(self, image_path, context): # New method
        chat_id = context.get("chat_id")
        message_thread_id = context.get("message_thread_id") # NEW: Get thread ID
        if chat_id:
            try:
                loop = asyncio.get_running_loop()
                with open(image_path, 'rb') as f:
                    await loop.run_in_executor(
                        None,
                        self.updater.bot.send_photo,
                        chat_id,
                        f,
                        message_thread_id=message_thread_id
                    )
                self.logger.info(f"Successfully sent image {image_path} to Telegram chat {chat_id}")
            except Exception as e:
                self.logger.error(f"Failed to send image {image_path} to Telegram chat {chat_id}: {e}")