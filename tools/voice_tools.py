from agent_network.tools.base_tool import BaseTool
import logging
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class MakePhoneCallTool(BaseTool):
    """Makes a real phone call via Twilio and speaks a message using TwiML."""

    def __init__(self):
        super().__init__(
            name="make_phone_call",
            description=(
                "Makes a phone call using Twilio and speaks a message to the recipient. "
                "Requires 'to_number' (E.164 format like +12065551234) and 'message' (text to speak). "
                "Optional: 'voice' (default 'alice'), 'language' (default 'en-US')."
            )
        )

    def run(self, to_number: str, message: str, voice: str = "alice", language: str = "en-US", **kwargs) -> Dict[str, Any]:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        from_number = os.environ.get("TWILIO_PHONE_NUMBER", "")

        if not account_sid or not auth_token:
            return {"status": "error", "output": "Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in Admin Settings."}
        if not from_number:
            return {"status": "error", "output": "TWILIO_PHONE_NUMBER not configured. Set it in Admin Settings."}
        if not to_number:
            return {"status": "error", "output": "to_number is required (E.164 format, e.g. +12065551234)."}

        try:
            from twilio.rest import Client
            from twilio.twiml.voice_response import VoiceResponse

            client = Client(account_sid, auth_token)

            # Build TwiML to speak the message
            twiml = VoiceResponse()
            twiml.say(message, voice=voice, language=language)

            call = client.calls.create(
                to=to_number,
                from_=from_number,
                twiml=str(twiml)
            )

            logger.info(f"[MakePhoneCallTool] Call initiated: SID={call.sid}, to={to_number}, status={call.status}")
            return {
                "status": "success",
                "output": f"Phone call initiated to {to_number}. Call SID: {call.sid}. Status: {call.status}.",
                "call_sid": call.sid
            }
        except ImportError:
            return {"status": "error", "output": "twilio package not installed. Run: pip install twilio"}
        except Exception as e:
            logger.error(f"[MakePhoneCallTool] Error: {e}", exc_info=True)
            return {"status": "error", "output": f"Failed to make call: {e}"}


class SendSMSTool(BaseTool):
    """Sends an SMS message via Twilio."""

    def __init__(self):
        super().__init__(
            name="send_sms",
            description=(
                "Sends an SMS text message using Twilio. "
                "Requires 'to_number' (E.164 format like +12065551234) and 'message' (text to send). "
                "Max 1600 characters."
            )
        )

    def run(self, to_number: str, message: str, **kwargs) -> Dict[str, Any]:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        from_number = os.environ.get("TWILIO_PHONE_NUMBER", "")

        if not account_sid or not auth_token:
            return {"status": "error", "output": "Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in Admin Settings."}
        if not from_number:
            return {"status": "error", "output": "TWILIO_PHONE_NUMBER not configured. Set it in Admin Settings."}
        if not to_number:
            return {"status": "error", "output": "to_number is required (E.164 format, e.g. +12065551234)."}

        try:
            from twilio.rest import Client

            client = Client(account_sid, auth_token)
            sms = client.messages.create(
                body=message[:1600],
                from_=from_number,
                to=to_number
            )

            logger.info(f"[SendSMSTool] SMS sent: SID={sms.sid}, to={to_number}, status={sms.status}")
            return {
                "status": "success",
                "output": f"SMS sent to {to_number}. Message SID: {sms.sid}. Status: {sms.status}.",
                "message_sid": sms.sid
            }
        except ImportError:
            return {"status": "error", "output": "twilio package not installed. Run: pip install twilio"}
        except Exception as e:
            logger.error(f"[SendSMSTool] Error: {e}", exc_info=True)
            return {"status": "error", "output": f"Failed to send SMS: {e}"}


class CheckCallStatusTool(BaseTool):
    """Checks the status of a Twilio phone call by its SID."""

    def __init__(self):
        super().__init__(
            name="check_call_status",
            description=(
                "Checks the status of a phone call by its Call SID. "
                "Requires 'call_sid'. Returns call status, duration, direction, etc."
            )
        )

    def run(self, call_sid: str, **kwargs) -> Dict[str, Any]:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

        if not account_sid or not auth_token:
            return {"status": "error", "output": "Twilio credentials not configured."}
        if not call_sid:
            return {"status": "error", "output": "call_sid is required."}

        try:
            from twilio.rest import Client

            client = Client(account_sid, auth_token)
            call = client.calls(call_sid).fetch()

            return {
                "status": "success",
                "output": f"Call {call_sid}: status={call.status}, duration={call.duration}s, direction={call.direction}",
                "call_status": call.status,
                "duration": call.duration,
                "direction": call.direction,
                "from": call.from_formatted,
                "to": call.to_formatted
            }
        except ImportError:
            return {"status": "error", "output": "twilio package not installed. Run: pip install twilio"}
        except Exception as e:
            logger.error(f"[CheckCallStatusTool] Error: {e}", exc_info=True)
            return {"status": "error", "output": f"Failed to check call status: {e}"}


class SynthesizeSpeechTool(BaseTool):
    """Text-to-speech using Edge TTS (free, no API key needed)."""

    def __init__(self):
        super().__init__(
            name="synthesize_speech",
            description=(
                "Converts text into spoken audio (MP3) using Microsoft Edge TTS (free). "
                "Requires 'text' and 'output_file_path'. "
                "Optional: 'voice' (default 'en-US-JennyNeural'), 'rate' (e.g. '+20%'), 'volume' (e.g. '-10%')."
            )
        )

    def run(self, text: str, output_file_path: str, voice: str = "en-US-JennyNeural",
            rate: str = "+0%", volume: str = "+0%", **kwargs) -> Dict[str, Any]:
        try:
            import edge_tts
            import asyncio

            os.makedirs(os.path.dirname(output_file_path) if os.path.dirname(output_file_path) else ".", exist_ok=True)

            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)

            # Run the async save in a new event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(asyncio.run, communicate.save(output_file_path)).result()
                else:
                    loop.run_until_complete(communicate.save(output_file_path))
            except RuntimeError:
                asyncio.run(communicate.save(output_file_path))

            logger.info(f"[SynthesizeSpeechTool] Audio saved to {output_file_path}")
            return {"status": "success", "output": f"Speech synthesized and saved to {output_file_path}"}
        except ImportError:
            return {"status": "error", "output": "edge_tts package not installed. Run: pip install edge-tts"}
        except Exception as e:
            logger.error(f"[SynthesizeSpeechTool] Error: {e}", exc_info=True)
            return {"status": "error", "output": f"Speech synthesis failed: {e}"}


class TranscribeVoiceTool(BaseTool):
    """Transcribes audio using Google Cloud STT if available, otherwise returns an error."""

    def __init__(self):
        super().__init__(
            name="transcribe_voice",
            description=(
                "Transcribes audio from a WAV file to text. "
                "Requires 'audio_file_path'. Optional: 'language' (default 'en-US'). "
                "Uses Google Cloud Speech-to-Text if credentials are configured."
            )
        )

    def run(self, audio_file_path: str, language: str = "en-US", **kwargs) -> Dict[str, Any]:
        if not os.path.exists(audio_file_path):
            return {"status": "error", "output": f"Audio file not found: {audio_file_path}"}

        try:
            from google.cloud import speech

            client = speech.SpeechClient()
            with open(audio_file_path, "rb") as f:
                content = f.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language,
            )

            response = client.recognize(config=config, audio=audio)
            transcript = " ".join(
                result.alternatives[0].transcript for result in response.results
            )

            logger.info(f"[TranscribeVoiceTool] Transcription: '{transcript.strip()}'")
            return {"status": "success", "output": transcript.strip() or "(no speech detected)"}

        except ImportError:
            return {"status": "error", "output": "Google Cloud Speech library not installed. Run: pip install google-cloud-speech"}
        except Exception as e:
            logger.error(f"[TranscribeVoiceTool] Error: {e}", exc_info=True)
            return {"status": "error", "output": f"Transcription failed: {e}"}


class ColdCallTool(BaseTool):
    """Orchestrates a cold call: synthesizes speech, makes the call via Twilio."""

    def __init__(self):
        super().__init__(
            name="cold_call",
            description=(
                "Executes a cold call sequence: synthesizes a script with TTS, "
                "then calls the number via Twilio and speaks the message. "
                "Requires 'phone_number' and 'call_script' (the text to speak). "
                "Optional: 'contact_name', 'voice' (Twilio voice, default 'alice')."
            )
        )

    def run(self, phone_number: str, call_script: str, contact_name: str = "Unknown",
            voice: str = "alice", **kwargs) -> Dict[str, Any]:
        if not phone_number:
            return {"status": "error", "output": "phone_number is required."}
        if not call_script:
            return {"status": "error", "output": "call_script is required."}

        logger.info(f"[ColdCallTool] Starting cold call to {contact_name} ({phone_number})")

        # Use MakePhoneCallTool to place the call with the script
        call_tool = MakePhoneCallTool()
        result = call_tool.run(to_number=phone_number, message=call_script, voice=voice)

        if result["status"] == "success":
            return {
                "status": "success",
                "output": f"Cold call to {contact_name} ({phone_number}) initiated. {result['output']}",
                "call_sid": result.get("call_sid")
            }
        else:
            return {
                "status": "error",
                "output": f"Cold call to {contact_name} failed: {result['output']}"
            }
