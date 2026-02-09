import logging
import asyncio
import threading
import os


from flask import Flask, request # Using Flask for webhook
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client as TwilioClient

from agent_network.connectors.base_connector import BaseConnector
from agent_network.tools.voice_tools import SynthesizeSpeechTool, TranscribeVoiceTool # Import the tools

logger = logging.getLogger(__name__)

# Load Twilio credentials from environment variables
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER") # The number assigned to Twilio

class VoiceConnector(BaseConnector):
    def __init__(self, agent, logger, port=5002):
        super().__init__(agent, logger)
        self.app = Flask(__name__)
        self.port = port
        self.host = "0.0.0.0" # Listen on all interfaces
        self.server_thread = None
        self.twilio_client = None

        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            self.twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        else:
            self.logger.warning("Twilio credentials not found in environment variables. Outbound calls and advanced Twilio features will be disabled.")
        
        # Initialize voice tools
        self.synthesize_speech_tool = SynthesizeSpeechTool()
        self.transcribe_voice_tool = TranscribeVoiceTool()

        # Register webhook route
        self._register_routes()
        self.logger.info(f"VoiceConnector initialized on port {self.port}.")

    def _twilio_webhook_handler(self):
        self.logger.info("Received Twilio webhook request.")
        response = VoiceResponse()
        
        # Get data from Twilio request
        call_sid = request.form.get('CallSid')
        speech_result = request.form.get('SpeechResult')
        input_received = request.form.get('Input', request.form.get('SpeechResult')) # Use 'Input' for generic input, fallback to SpeechResult
        
        # Retrieve agent name from the connector's agent instance
        agent_name = self.agent.name 

        # A simple way to manage state for now: assume initial call vs subsequent input
        # In a real app, use Twilio Sync or a database for persistent state
        if input_received:
            self.logger.info(f"Speech/Input result from Twilio for {agent_name}: '{input_received}' (CallSid: {call_sid})")
            
            # Pass the speech result to the agent
            # Use asyncio.run to execute the async agent processing in this synchronous Flask route
            try:
                # The agent's process_user_message needs to be adapted to return a text response
                # For now, simulate a response or ensure the agent method exists and returns a string
                agent_response_text = asyncio.run(self.agent.process_connector_message(input_received, context={'call_sid': call_sid, 'source': 'voice', 'from_number': request.form.get('From')}))
                self.logger.info(f"Agent '{agent_name}' responded with: '{agent_response_text}'")
            except Exception as e:
                self.logger.error(f"Error processing message with agent '{agent_name}': {e}", exc_info=True)
                agent_response_text = "I encountered an error trying to process your request. Please try again."

            if agent_response_text:
                response.say(agent_response_text)
            else:
                response.say("I didn't quite understand that. Can you please rephrase?")

            # Continue gathering input for multi-turn conversation
            gather = Gather(input='speech', speechTimeout='auto', action='/twilio-webhook', method='POST')
            response.append(gather)
            response.say("I didn't hear anything. Please try again.") # If no speech is detected after gather
        else:
            # Initial greeting or no speech detected in a subsequent turn
            greeting_text = "Hello, I am your agent, " + agent_name + ". How can I help you today?"
            response.say(greeting_text)
            
            # Gather speech input after greeting
            gather = Gather(input='speech', speechTimeout='auto', action='/twilio-webhook', method='POST')
            response.append(gather)
            response.say("I didn't hear anything. Please try again.") # If no speech is detected after gather
        
        return str(response)

    def _register_routes(self):
        # Register the webhook handler function manually
        self.app.add_url_rule("/twilio-webhook", "twilio_webhook", self._twilio_webhook_handler, methods=["POST"])

        # Removed the /audio/<filename> route as we are using response.say() now.

    def _run_flask_app(self):
        # Use a silent reloader or disable it for production.
        # For development, you might want debug=True.
        # For deployment, consider waitress.serve for production-grade WSGI server.
        try:
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)
        except Exception as e:
            self.logger.error(f"Flask app for VoiceConnector failed: {e}")

    def start(self):
        self.server_thread = threading.Thread(target=self._run_flask_app, daemon=True)
        self.server_thread.start()
        self.logger.info(f"VoiceConnector Flask server started on http://{self.host}:{self.port}/")
        self.logger.info(f"Twilio webhook URL should be configured to point to http://YOUR_PUBLIC_URL:{self.port}/twilio-webhook")

    def stop(self):
        # This is a soft stop. For a clean shutdown in production,
        # you'd typically need to signal the Flask development server
        # or the WSGI server (like Waitress) to shut down.
        self.logger.info("VoiceConnector stopping...")
        # A more robust shutdown mechanism for Flask/Waitress would be needed for production
        if self.server_thread and self.server_thread.is_alive():
            # In a real scenario, you'd send a request to a shutdown endpoint
            # or use a proper WSGI server's shutdown mechanism.
            # For a simple development server, setting daemon=True and letting the main thread exit works.
            pass # The daemon thread will exit when the main program exits
        self.logger.info("VoiceConnector stopped.")

    async def send_response(self, response_text: str, context: dict):
        # For voice, this would typically involve synthesizing speech and
        # playing it on an active call. This function needs to be
        # reconsidered in the context of an ongoing Twilio call.
        # It's not a direct "send and forget" like text messages.
        # For now, it will just log that a response would have been sent.
        self.logger.info(f"VoiceConnector would have sent response: '{response_text}' to call {context.get('call_sid', 'N/A')}")
        # In a full implementation, you might queue this response to be played
        # during the next Twilio <Gather> or <Say> action.
        pass

    async def send_image(self, image_path: str, context: dict):
        self.logger.warning("VoiceConnector does not support sending images directly in a voice call.")
        pass

# Example of how to add this connector in main_agent_entrypoint.py
# (This part is illustrative and not to be added to voice_connector.py)
"""
# In main_agent_entrypoint.py, update get_connector_class and the main loop:
# Add 'voice' to the choices
# elif connector_type_choice == "voice":
#     voice_port = os.environ.get(f"{agent_name.upper()}_VOICE_PORT", "5002") # Default port for voice
#     connector = ConnectorClass(agent=agent, logger=logger, port=int(voice_port))
"""
