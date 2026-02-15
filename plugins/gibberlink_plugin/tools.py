import logging
import os
import zlib
import base64
import struct
import wave
import requests
from typing import Dict, Any

from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# Protocol markers
GL_HELLO = "[GL:HELLO]"
GL_ACK = "[GL:ACK]"
GL_DATA = "[GL:DATA]"

# Track handshake state between agent pairs
_handshake_state = {}


def _compress_message(message: str) -> str:
    """Compress a message: zlib compress -> base64 encode -> prefix with GL_DATA."""
    compressed = zlib.compress(message.encode("utf-8"), level=9)
    encoded = base64.b64encode(compressed).decode("ascii")
    return f"{GL_DATA}{encoded}"


def _decompress_message(encoded: str) -> str:
    """Decompress a GL_DATA message: strip prefix -> base64 decode -> zlib decompress."""
    raw = encoded[len(GL_DATA):]
    compressed = base64.b64decode(raw)
    return zlib.decompress(compressed).decode("utf-8")


class GibberLinkEncodeTool(BaseTool):
    """Encodes a message using the GibberLink compressed protocol."""

    def __init__(self):
        super().__init__(
            name="gibberlink_encode",
            description=(
                "Encodes a message using the GibberLink AI-to-AI protocol. "
                "Mode 'text' (default): compresses with zlib+base64, returns string with [GL:DATA] prefix. "
                "Mode 'audio': encodes message as audio using ggwave data-over-sound, returns WAV file path. "
                "Requires 'message'. Optional: 'mode' ('text' or 'audio'), 'output_file_path' (for audio mode)."
            )
        )

    def run(self, message: str, mode: str = "text", output_file_path: str = None, **kwargs) -> Dict[str, Any]:
        if not message:
            return {"status": "error", "output": "message is required."}

        if mode == "text":
            encoded = _compress_message(message)
            original_len = len(message)
            compressed_len = len(encoded)
            ratio = round((1 - compressed_len / original_len) * 100, 1) if original_len > 0 else 0
            return {
                "status": "success",
                "output": f"Message encoded ({original_len} -> {compressed_len} chars, {ratio}% smaller).",
                "encoded_message": encoded,
                "compression_ratio": ratio
            }

        elif mode == "audio":
            try:
                import ggwave

                if not output_file_path:
                    os.makedirs("temp_audio", exist_ok=True)
                    output_file_path = f"temp_audio/gibberlink_{hash(message) & 0xFFFFFFFF}.wav"

                os.makedirs(os.path.dirname(output_file_path) if os.path.dirname(output_file_path) else ".", exist_ok=True)

                # ggwave encode returns raw audio samples (16-bit signed int, 48kHz mono)
                waveform = ggwave.encode(message, protocolId=1, volume=20)

                # Write as WAV file
                with wave.open(output_file_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(48000)
                    wf.writeframes(waveform)

                logger.info(f"[GibberLinkEncode] Audio encoded to {output_file_path}")
                return {
                    "status": "success",
                    "output": f"Message encoded as audio: {output_file_path}",
                    "audio_file_path": output_file_path
                }
            except ImportError:
                return {"status": "error", "output": "ggwave not installed. Run: pip install ggwave"}
            except Exception as e:
                logger.error(f"[GibberLinkEncode] Audio encode error: {e}", exc_info=True)
                return {"status": "error", "output": f"Audio encoding failed: {e}"}
        else:
            return {"status": "error", "output": f"Unknown mode '{mode}'. Use 'text' or 'audio'."}


class GibberLinkDecodeTool(BaseTool):
    """Decodes a GibberLink-encoded message."""

    def __init__(self):
        super().__init__(
            name="gibberlink_decode",
            description=(
                "Decodes a GibberLink-encoded message. "
                "Detects protocol markers: [GL:HELLO] (handshake init), [GL:ACK] (handshake confirm), "
                "[GL:DATA] (compressed data). Can also decode ggwave audio files. "
                "Provide 'encoded_message' for text, or 'audio_file_path' for audio."
            )
        )

    def run(self, encoded_message: str = None, audio_file_path: str = None, **kwargs) -> Dict[str, Any]:
        # Audio mode
        if audio_file_path:
            try:
                import ggwave

                if not os.path.exists(audio_file_path):
                    return {"status": "error", "output": f"Audio file not found: {audio_file_path}"}

                with wave.open(audio_file_path, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())

                instance = ggwave.init()
                decoded = ggwave.decode(instance, frames)
                ggwave.free(instance)

                if decoded is None:
                    return {"status": "error", "output": "Could not decode audio. No GibberLink data found."}

                text = decoded.decode("utf-8") if isinstance(decoded, bytes) else str(decoded)
                logger.info(f"[GibberLinkDecode] Audio decoded: '{text}'")
                return {"status": "success", "output": text, "decoded_message": text, "mode": "audio"}

            except ImportError:
                return {"status": "error", "output": "ggwave not installed. Run: pip install ggwave"}
            except Exception as e:
                logger.error(f"[GibberLinkDecode] Audio decode error: {e}", exc_info=True)
                return {"status": "error", "output": f"Audio decoding failed: {e}"}

        # Text mode
        if not encoded_message:
            return {"status": "error", "output": "Provide 'encoded_message' or 'audio_file_path'."}

        # Check for handshake markers
        if encoded_message.startswith(GL_HELLO):
            remainder = encoded_message[len(GL_HELLO):].strip()
            return {
                "status": "success",
                "output": f"Handshake initiated. Plain message: '{remainder}'",
                "protocol": "handshake_hello",
                "decoded_message": remainder,
                "is_ai": True
            }

        if encoded_message.startswith(GL_ACK):
            remainder = encoded_message[len(GL_ACK):].strip()
            return {
                "status": "success",
                "output": f"Handshake confirmed. Plain message: '{remainder}'",
                "protocol": "handshake_ack",
                "decoded_message": remainder,
                "is_ai": True
            }

        # Compressed data
        if encoded_message.startswith(GL_DATA):
            try:
                decoded = _decompress_message(encoded_message)
                logger.info(f"[GibberLinkDecode] Decompressed: '{decoded}'")
                return {
                    "status": "success",
                    "output": decoded,
                    "decoded_message": decoded,
                    "protocol": "compressed",
                    "mode": "text"
                }
            except Exception as e:
                logger.error(f"[GibberLinkDecode] Decompress error: {e}")
                return {"status": "error", "output": f"Failed to decompress: {e}"}

        # No protocol marker — plain text
        return {
            "status": "success",
            "output": encoded_message,
            "decoded_message": encoded_message,
            "protocol": "plain",
            "mode": "text"
        }


class GibberLinkSendTool(BaseTool):
    """Sends a message to another agent using the GibberLink protocol with auto-handshake."""

    def __init__(self):
        super().__init__(
            name="gibberlink_send",
            description=(
                "Sends a message to another agent using the GibberLink AI-to-AI protocol. "
                "On first contact, includes a [GL:HELLO] handshake marker. "
                "After handshake is confirmed, messages are automatically compressed. "
                "Requires 'target_agent' (agent name) and 'message' (text to send). "
                "Also needs 'sender_agent_name' (your agent name)."
            )
        )
        self.hub_url = os.environ.get("HUB_URL", "http://127.0.0.1:5000")

    def run(self, target_agent: str, message: str, sender_agent_name: str = "unknown", **kwargs) -> Dict[str, Any]:
        if not target_agent:
            return {"status": "error", "output": "target_agent is required."}
        if not message:
            return {"status": "error", "output": "message is required."}

        pair_key = f"{sender_agent_name}->{target_agent}"
        handshake_done = _handshake_state.get(pair_key, False)

        if handshake_done:
            # Compress the message
            encoded = _compress_message(message)
            wire_message = encoded
            protocol_used = "compressed"
            logger.info(f"[GibberLinkSend] Sending compressed message to {target_agent} ({len(message)} -> {len(encoded)} chars)")
        else:
            # Send with handshake marker
            wire_message = f"{GL_HELLO} {message}"
            protocol_used = "handshake_hello"
            # Mark that we initiated handshake (will complete when we see ACK)
            _handshake_state[pair_key] = False
            logger.info(f"[GibberLinkSend] Initiating handshake with {target_agent}")

        # Send via hub
        try:
            payload = {
                "target_agent_name": target_agent,
                "message": wire_message,
                "sender_agent_name": sender_agent_name
            }
            response = requests.post(
                f"{self.hub_url}/send_message_to_agent_by_name",
                json=payload,
                timeout=5
            )
            response.raise_for_status()

            return {
                "status": "success",
                "output": f"Message sent to {target_agent} via GibberLink ({protocol_used}).",
                "protocol_used": protocol_used,
                "compressed": handshake_done
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[GibberLinkSend] Failed to send: {e}")
            return {"status": "error", "output": f"Failed to send message: {e}"}

    @staticmethod
    def confirm_handshake(sender: str, receiver: str):
        """Call this when a [GL:ACK] is received to complete the handshake."""
        pair_key = f"{receiver}->{sender}"
        _handshake_state[pair_key] = True
        logger.info(f"[GibberLink] Handshake confirmed: {pair_key}")


def get_tools():
    """Entry point for plugin discovery."""
    logger.info("Initializing GibberLink Protocol plugin tools.")
    try:
        tools = [
            GibberLinkEncodeTool(),
            GibberLinkDecodeTool(),
            GibberLinkSendTool()
        ]
        logger.info(f"GibberLink plugin loaded: {[t.name for t in tools]}")
        return tools
    except Exception as e:
        logger.error(f"Error creating GibberLink tools: {e}", exc_info=True)
        return []
