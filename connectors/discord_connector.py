import discord
import threading
import asyncio
import os
import uuid
from agent_network.connectors.base_connector import BaseConnector

class DiscordConnector(BaseConnector):
    def __init__(self, agent, logger, token, channel_id):
        super().__init__(agent, logger)
        if not token or not channel_id:
            raise ValueError("Discord token and channel ID are required for the Discord connector.")
        self.token = token
        self.channel_id = int(channel_id)
        
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        
        self.client = discord.Client(intents=intents)
        self.thread = None
        self.loop = None

        @self.client.event
        async def on_ready():
            self.logger.info(f'Discord bot logged in as {self.client.user}')

        @self.client.event
        async def on_message(message):
            if message.author == self.client.user:
                return

            channel_id = message.channel.id
            thread_id = None
            
            # Check if the message is in a thread
            if isinstance(message.channel, discord.Thread):
                thread_id = message.channel.id
                # Ensure the thread is in the configured parent channel
                if message.channel.parent_id != self.channel_id:
                    return
            # If not in a thread, ensure it's in the configured channel
            elif channel_id != self.channel_id:
                return
            
            self.logger.info(f"Received message from Discord user {message.author} in channel {channel_id}, thread {thread_id}: {message.content}")
            
            image_path = None
            if message.attachments:
                for attachment in message.attachments:
                    if 'image' in attachment.content_type:
                        try:
                            temp_dir = "temp_attachments"
                            os.makedirs(temp_dir, exist_ok=True)
                            filename = f"{temp_dir}/{uuid.uuid4()}_{attachment.filename}"
                            await attachment.save(filename)
                            image_path = filename
                            self.logger.info(f"Downloaded image attachment: {image_path}")
                            break
                        except Exception as e:
                            self.logger.error(f"Failed to download Discord attachment: {e}")

            session_id = f"discord_{self.channel_id}_{thread_id}" if thread_id else f"discord_{channel_id}"
            context = {
                "connector": self, 
                "channel_id": self.channel_id, # Always use the parent channel ID for context
                "thread_id": thread_id,
                "author": message.author.name,
                "session_id": session_id,
                "timestamp": message.created_at.isoformat() # Add gateway timestamp
            }
            self.agent.handle_message(message.content, context, image_path=image_path)

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.logger.info("Discord connector started in a background thread.")

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.client.run(self.token)
        except discord.errors.LoginFailure:
            self.logger.error("LOGIN FAILED: Could not log in to Discord. Please check your bot token.")
        except Exception as e:
            self.logger.error(f"An error occurred in the Discord connector thread: {e}")

    def stop(self):
        if self.client.is_running():
            self.logger.info("Stopping Discord connector...")
            # Use run_coroutine_threadsafe to call async close from this synchronous method
            future = asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)
            try:
                future.result(timeout=5) # Wait for the client to close
            except Exception as e:
                self.logger.error(f"Error while stopping Discord client: {e}")
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.logger.info("Discord connector stopped.")

    async def send_response(self, response_text, context):
        # Reply to the thread if a thread_id is present, otherwise reply to the channel
        target_channel_id = context.get("thread_id") or context.get("channel_id")
        if target_channel_id:
            try:
                target = self.client.get_channel(target_channel_id)
                if not target:
                    target = await self.client.fetch_channel(target_channel_id)
                
                if target:
                    await target.send(response_text)
                else:
                    self.logger.error(f"Could not find Discord channel/thread with ID: {target_channel_id}")
            except Exception as e:
                self.logger.error(f"Failed to send message to Discord channel/thread {target_channel_id}: {e}")

    async def send_image(self, image_path, context):
        # Reply to the thread if a thread_id is present, otherwise reply to the channel
        target_channel_id = context.get("thread_id") or context.get("channel_id")
        if target_channel_id:
            try:
                target = self.client.get_channel(target_channel_id)
                if not target:
                    target = await self.client.fetch_channel(target_channel_id)

                if target:
                    with open(image_path, 'rb') as f:
                        picture = discord.File(f)
                        await target.send(file=picture)
                    self.logger.info(f"Successfully sent image {image_path} to Discord channel/thread {target_channel_id}")
                else:
                    self.logger.error(f"Could not find Discord channel/thread with ID: {target_channel_id} to send image.")
            except Exception as e:
                self.logger.error(f"Failed to send image {image_path} to Discord channel/thread {target_channel_id}: {e}")
