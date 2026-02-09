from agent_network.tools.base_tool import BaseTool
import logging
import asyncio
from typing import Dict, Any, Optional
import os # NEW: For file path operations
from google.cloud import texttospeech # NEW: For Google Cloud TTS
from google.cloud import speech # NEW: For Google Cloud STT
from google.protobuf.json_format import MessageToJson # NEW: For serializing STT response if needed

import time # NEW: For simulated call_id
# import aiohttp # Potentially for AMI client if using websockets or HTTP

logger = logging.getLogger(__name__)

# --- NEW: Asterisk Manager Interface (AMI) Client (Placeholder) ---
# This would be a more robust client in a full implementation,
# likely using an existing library like Pystx or a custom async client.
class AmiClient:
    def __init__(self, host: str, username: str, secret: str):
        self.host = host
        self.username = username
        self.secret = secret
        self.connected = False
        logger.info(f"[AmiClient]: Initialized for host {host}, user {username}")

    async def connect(self) -> bool:
        # Simulate connection to AMI
        logger.info(f"[AmiClient]: Simulating connection to AMI at {self.host} for user {self.username}...")
        await asyncio.sleep(1) # Simulate network delay
        self.connected = True
        logger.info(f"[AmiClient]: Simulated connection to AMI successful.")
        return True

    async def disconnect(self):
        # Simulate disconnection from AMI
        logger.info(f"[AmiClient]: Simulating disconnection from AMI...")
        await asyncio.sleep(0.5)
        self.connected = False
        logger.info(f"[AmiClient]: Simulated disconnection successful.")

    async def originate_call(self, channel: str, context: str, exten: str, priority: int = 1, application: str = None, data: str = None) -> Dict[str, Any]:
        """
        Simulates originating a call via AMI.
        channel: e.g., 'SIP/my_trunk/phone_number' or 'SIP/extension'
        context: The context in extensions.conf
        exten: The extension to dial in the context
        """
        if not self.connected:
            return {"status": "error", "message": "Not connected to AMI."}

        logger.info(f"[AmiClient]: Simulating AMI Originate: Channel={channel}, Context={context}, Exten={exten}, App={application}, Data={data}")
        await asyncio.sleep(2) # Simulate call setup time
        
        # Simulate successful origination
        if channel.startswith("SIP/") or channel.isdigit(): # Basic check for SIP channel or internal extension
            logger.info(f"[AmiClient]: Simulated call originated successfully to {channel}.")
            return {"status": "success", "message": "Simulated call originated.", "call_id": f"simulated_call_{time.time()}"}
        else:
            logger.warning(f"[AmiClient]: Simulated call origination failed for invalid channel: {channel}.")
            return {"status": "error", "message": "Simulated call origination failed: Invalid channel format."}

    async def playback(self, channel: str, filename: str) -> Dict[str, Any]:
        """Simulates playing a file on a channel via AMI."""
        if not self.connected:
            return {"status": "error", "message": "Not connected to AMI."}
        logger.info(f"[AmiClient]: Simulating AMI Playback on {channel} with file {filename}...")
        await asyncio.sleep(1) # Simulate playback time
        return {"status": "success", "message": "Simulated playback initiated."}

    async def get_variable(self, channel: str, variable: str) -> Dict[str, Any]:
        """Simulates getting a channel variable via AMI."""
        if not self.connected:
            return {"status": "error", "message": "Not connected to AMI."}
        logger.info(f"[AmiClient]: Simulating AMI GetVariable for {channel} variable {variable}...")
        await asyncio.sleep(0.5)
        # Simulate a common variable, e.g., "DIALSTATUS"
        simulated_value = "ANSWER" if "DIALSTATUS" in variable.upper() else "SIM_VALUE"
        return {"status": "success", "message": "Simulated variable retrieved.", "variable": variable, "value": simulated_value}

# Set Google Application Credentials environment variable
# This assumes the user will place their service account key file
# in the project root and configure its path via configure_agent.py
# If GOOGLE_APPLICATION_CREDENTIALS is not set, the clients will look for it
# in default locations, or need explicit credential passing.
# For simplicity, we'll guide the user to set it via env variable.


class MakePhoneCallTool(BaseTool):
    def __init__(self, ami_client: Optional[AmiClient] = None):
        super().__init__(
            name="make_phone_call",
            description="Initiates a phone call. Requires 'message' (text to speak). Can call 'to_number' (external PSTN, simulated with cost warning) or 'internal_extension' (simulated free internal call). Specify either 'to_number' OR 'internal_extension'. NOTE: External calls are simulated and incur costs with real VoIP providers."
        )
        self.ami_client = ami_client # AmiClient instance, if FreePBX is configured

    async def run(self, message: str, to_number: Optional[str] = None, internal_extension: Optional[str] = None) -> Dict[str, Any]:
        if to_number and internal_extension:
            return {"status": "error", "message": "Specify either 'to_number' or 'internal_extension', not both."}
        if not to_number and not internal_extension:
            return {"status": "error", "message": "Specify either 'to_number' or 'internal_extension'."}

        if to_number:
            logger.info(f"[MakePhoneCallTool]: SIMULATED EXTERNAL CALL: Attempting to call {to_number} and say: '{message}'")
            logger.warning("NOTE: This is a simulation for an external call. Real phone calls to PSTN numbers require integration with a VoIP provider (like Twilio) and will incur charges. Configure a VOIP_API_SERVICE in configure_agent.py for real external calls.")
            target = to_number
            call_type = "external_pstn"
        elif internal_extension:
            logger.info(f"[MakePhoneCallTool]: Attempting to call internal extension {internal_extension} with message: '{message}'")
            target = internal_extension
            call_type = "internal_extension"

            if self.ami_client:
                # Simulate AMI interaction for internal calls
                if not self.ami_client.connected:
                    await self.ami_client.connect() # Connect if not already

                # Assume a default context for FreePBX internal calls for simulation
                ami_result = await self.ami_client.originate_call(
                    channel=f"SIP/{internal_extension}", # Assuming SIP extension
                    context="from-internal", # Common FreePBX context
                    exten=internal_extension,
                    priority=1
                )
                
                if ami_result["status"] == "success":
                    logger.info(f"[MakePhoneCallTool]: FreePBX simulated internal call originated to {internal_extension}. Playing message...")
                    # In a real scenario, you'd integrate TTS to play the message over the call
                    # For now, simulate playback
                    await asyncio.sleep(2) # Simulate message playback time
                    return {"status": "success", "output": f"FreePBX simulated internal call to {internal_extension} initiated with message '{message}'."}
                else:
                    return {"status": "error", "message": f"FreePBX simulated internal call failed: {ami_result['message']}"}
            else:
                logger.info(f"[MakePhoneCallTool]: Simulating internal call as no FreePBX AMI client is configured.")
                logger.info("NOTE: For real FreePBX internal calls, ensure a FreePBX/Asterisk AMI client is configured.")

        # Simulate call initiation and message playing for generic case or external
        await asyncio.sleep(3) # Simulate call setup and message playback
        logger.info(f"[MakePhoneCallTool]: Simulated {call_type} call to {target} initiated. Message '{message}' simulated as played.")
        return {"status": "success", "output": f"Simulated {call_type} call to {target} initiated with message '{message}'."}

class TranscribeVoiceTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="transcribe_voice",
            description="Transcribes a segment of recorded voice audio (WAV format) into text using Google Cloud Speech-to-Text. Requires 'audio_file_path' as an argument. Make sure GOOGLE_APPLICATION_CREDENTIALS environment variable is set."
        )
        self.client = speech.SpeechClient()

    async def run(self, audio_file_path: str):
        if not os.path.exists(audio_file_path):
            logger.error(f"[TranscribeVoiceTool]: Audio file not found at {audio_file_path}")
            return {"status": "error", "message": f"Audio file not found at {audio_file_path}"}
        
        # Determine audio format (assuming WAV for now)
        # For more robust solution, inspect file header or allow format argument
        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, # Assuming common WAV format
            sample_rate_hertz=16000, # Common sample rate
            language_code="en-US",
        )

        try:
            logger.info(f"[TranscribeVoiceTool]: Transcribing audio from {audio_file_path} using Google Cloud STT...")
            response = self.client.recognize(config=config, audio=audio)
            
            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript + " "
            
            logger.info(f"[TranscribeVoiceTool]: Transcription complete. Text: '{transcript.strip()}'")
            return {"status": "success", "output": transcript.strip()}
        except Exception as e:
            logger.error(f"[TranscribeVoiceTool]: Error during Google Cloud STT transcription: {e}")
            return {"status": "error", "message": f"Google Cloud STT transcription failed: {e}"}

class SynthesizeSpeechTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="synthesize_speech",
            description="Converts text into spoken audio (WAV format) using Google Cloud Text-to-Speech. Requires 'text' and 'output_file_path' as arguments. Make sure GOOGLE_APPLICATION_CREDENTIALS environment variable is set."
        )
        self.client = texttospeech.TextToSpeechClient()

    async def run(self, text: str, output_file_path: str):
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16 # WAV format
        )

        try:
            logger.info(f"[SynthesizeSpeechTool]: Synthesizing speech for text: '{text}' into {output_file_path} using Google Cloud TTS...")
            response = self.client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            with open(output_file_path, "wb") as out_file:
                out_file.write(response.audio_content)
            
            logger.info(f"[SynthesizeSpeechTool]: Speech synthesis complete. Audio saved to {output_file_path}.")
            return {"status": "success", "output": output_file_path}
        except Exception as e:
            logger.error(f"[SynthesizeSpeechTool]: Error during Google Cloud TTS synthesis: {e}")
            return {"status": "error", "message": f"Google Cloud TTS synthesis failed: {e}"}

class ColdCallTool(BaseTool):
    def __init__(self, make_phone_call_tool: MakePhoneCallTool, synthesize_speech_tool: SynthesizeSpeechTool, transcribe_voice_tool: TranscribeVoiceTool):
        super().__init__(
            name="cold_call",
            description="Executes a simulated cold call to a contact. Requires 'contact_name', 'phone_number', 'call_script' (text for agent to speak), and 'expected_response_duration' (seconds for listening for a response). Outputs call outcome and transcribed response."
        )
        self.make_phone_call_tool = make_phone_call_tool
        self.synthesize_speech_tool = synthesize_speech_tool
        self.transcribe_voice_tool = transcribe_voice_tool

    async def run(self, contact_name: str, phone_number: str, call_script: str, expected_response_duration: int = 5) -> Dict[str, Any]:
        logger.info(f"[ColdCallTool]: Initiating simulated cold call to {contact_name} ({phone_number})...")
        call_outcome = {"status": "simulated_call_initiated", "message": f"Simulating call to {phone_number} for {contact_name}."}

        try:
            # Step 1: Synthesize the call script
            temp_dir = "temp_audio"
            os.makedirs(temp_dir, exist_ok=True)
            audio_output_path = os.path.join(temp_dir, f"call_script_{contact_name.replace(' ', '_')}_{asyncio.get_event_loop().time()}.wav")
            synthesis_result = await self.synthesize_speech_tool.run(text=call_script, output_file_path=audio_output_path)
            
            if synthesis_result["status"] != "success":
                return {"status": "error", "message": f"Failed to synthesize speech for call script: {synthesis_result['message']}"}
            
            # Step 2: "Make" the phone call (simulated)
            phone_call_result = await self.make_phone_call_tool.run(to_number=phone_number, message=f"Playing synthesized script from {audio_output_path}")
            
            if phone_call_result["status"] != "success":
                return {"status": "error", "message": f"Failed to simulate phone call: {phone_call_result['message']}"}

            # Step 3: Simulate listening for a response and transcribing
            logger.info(f"[ColdCallTool]: Simulating listening for {expected_response_duration} seconds...")
            await asyncio.sleep(expected_response_duration)
            
            # For simulation, we'll just generate a dummy transcription
            simulated_response_audio_path = os.path.join(temp_dir, f"response_{contact_name.replace(' ', '_')}_{asyncio.get_event_loop().time()}.wav")
            # In a real scenario, incoming audio would be saved to simulated_response_audio_path
            # We'll create a dummy file for the TranscribeVoiceTool to process
            with open(simulated_response_audio_path, "wb") as f:
                f.write(b"dummy audio content")

            logger.info(f"[ColdCallTool]: Simulated incoming audio saved to {simulated_response_audio_path}. Now transcribing...")

            # Simulate transcription of the response
            transcription_result = await self.transcribe_voice_tool.run(audio_file_path=simulated_response_audio_path)
            
            # Clean up dummy audio file
            os.remove(simulated_response_audio_path)

            transcribed_response = transcription_result["output"] if transcription_result["status"] == "success" else "Failed to transcribe simulated response."

            call_outcome = {
                "status": "success",
                "message": f"Simulated cold call to {contact_name} completed.",
                "call_script_played": call_script,
                "simulated_transcribed_response": transcribed_response,
                "cost_note": "NOTE: Real calls would incur charges from your VoIP provider."
            }
            logger.info(f"[ColdCallTool]: Simulated cold call outcome for {contact_name}: {call_outcome['message']}")
            return call_outcome

        except Exception as e:
            logger.error(f"[ColdCallTool]: Error during simulated cold call to {contact_name}: {e}")
            return {"status": "error", "message": f"Error during simulated cold call: {e}"}

# NEW: Edge TTS Tool
class EdgeTTSTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="edge_tts",
            description="Converts text into spoken audio (MP3 format) using Microsoft Edge's Text-to-Speech. Requires 'text' and 'output_file_path'. Optional args: 'voice' (e.g., 'en-US-JennyNeural'), 'rate' (e.g., '+20%'), 'volume' (e.g., '-10%')."
        )

    async def run(self, text: str, output_file_path: str, voice: str = "en-US-JennyNeural", rate: str = "+0%", volume: str = "+0%") -> Dict[str, Any]:
        try:
            # Basic path validation to prevent path traversal
            from agent_network.tools.file_tools import _validate_path # Import the helper
            validated_output_path = _validate_path(output_file_path, self.name)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(validated_output_path), exist_ok=True)

            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            logger.info(f"[EdgeTTSTool]: Synthesizing speech for text: '{text}' into {validated_output_path} using Edge TTS...")
            
            # Edge TTS is async, so run it
            await communicate.save(validated_output_path)
            
            logger.info(f"[EdgeTTSTool]: Speech synthesis complete. Audio saved to {validated_output_path}.")
            return {"status": "success", "output": validated_output_path}
        except ValueError as ve:
            return {"status": "error", "message": str(ve)}
        except Exception as e:
            logger.error(f"[EdgeTTSTool]: Error during Edge TTS synthesis: {e}", exc_info=True)
            return {"status": "error", "message": f"Edge TTS synthesis failed: {e}"}

