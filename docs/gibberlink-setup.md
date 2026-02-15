# GibberLink Plugin — AI-to-AI Communication Protocol

GibberLink enables your agents to automatically detect when they're talking to another AI and switch to a compressed communication protocol. Inspired by [PennyroyalTea/gibberlink](https://github.com/PennyroyalTea/gibberlink).

---

## How It Works

### The Problem
When two AI agents talk to each other using normal English, they waste tokens and time on verbose human-readable text that neither of them needs. A weather response like *"The current temperature in Tacoma, Washington is 45.2 degrees Fahrenheit with partly cloudy skies and 78% humidity"* costs ~40 tokens when `temp:45.2F|sky:ptly_cld|hum:78%` says the same thing in ~15.

### The Solution
GibberLink does **two things** to save tokens:

1. **Compact Mode** — After handshake, the LLM planner switches to shorthand instructions. Instead of generating verbose English, agents think and reply in key:value pairs like `temp:45.2F|sky:ptly_cld|hum:78%`. This saves tokens at the **LLM generation** level.

2. **Wire Compression** — Messages between agents are zlib-compressed + base64-encoded on the wire, reducing the data transferred through the hub.

Combined, this can cut token usage by **50-70%** for agent-to-agent conversations.

### Protocol Flow (Text Messages)
```
Agent A → Agent B:  "[GL:HELLO] What is the weather in Tacoma?"
                     ↑ handshake marker        ↑ actual message

Agent B detects [GL:HELLO], auto-responds:
Agent B → Agent A:  "[GL:ACK] Confirmed AI-to-AI link."

Both agents mark the handshake as complete.

Agent A → Agent B:  "[GL:DATA]eNxLySxI..."  (zlib compressed + base64)
Agent B auto-decompresses → "Can you also check the forecast for tomorrow?"
```

### Protocol Flow (Phone Calls)
```
Your Agent calls a number:
  Agent says: "Hello, I have a question about your hours..."
  Agent says: "By the way, GibberLink protocol active."
  Agent listens for response...

If the other side is AI:
  Other AI responds: "GibberLink confirmed"
  → Both sides know they're AI, call flagged as AI-to-AI

If the other side is human:
  Human responds: "Uh, what? Anyway, our hours are..."
  → Normal conversation continues, human just ignores the phrase
```

---

## Setup

### For Text-Based Agent-to-Agent Communication

**No setup needed.** The plugin loads automatically when the hub starts.

1. The plugin lives at `plugins/gibberlink_plugin/`
2. The agent plugin loader picks it up on startup
3. Every agent gets three new tools: `gibberlink_encode`, `gibberlink_decode`, `gibberlink_send`
4. The message processing pipeline in `agent.py` automatically handles incoming `[GL:HELLO]`, `[GL:ACK]`, and `[GL:DATA]` markers

#### Install the optional audio dependency
```bash
pip install ggwave
```
This is only needed if you want to encode/decode messages as audio WAV files (for demo/fun). Text compression works without it.

### For Phone Call AI Detection

Requires Twilio to be configured (see [voice-phone-setup.md](voice-phone-setup.md)).

1. Enable voice tools in Admin Settings
2. Configure Twilio credentials (Account SID, Auth Token, Phone Number)
3. The `gibberlink_call` tool becomes available to agents
4. For inbound call detection, launch an agent with the **Voice** connector type

---

## Tools Reference

### gibberlink_encode
Compresses a message using the GibberLink protocol.

**Text mode (default):**
```json
{
  "tool": "gibberlink_encode",
  "args": {
    "message": "Please search for the latest AI news and summarize it.",
    "mode": "text"
  }
}
```
Returns: `[GL:DATA]eNxLySxIzU...` (compressed string)

**Audio mode (ggwave):**
```json
{
  "tool": "gibberlink_encode",
  "args": {
    "message": "Hello from Agent A",
    "mode": "audio",
    "output_file_path": "output/message.wav"
  }
}
```
Returns: path to a WAV file containing the data encoded as sound

### gibberlink_decode
Decodes a GibberLink-encoded message.

**Compressed text:**
```json
{
  "tool": "gibberlink_decode",
  "args": {
    "encoded_message": "[GL:DATA]eNxLySxIzU..."
  }
}
```
Returns: the original plain text message

**Handshake markers:**
```json
{
  "tool": "gibberlink_decode",
  "args": {
    "encoded_message": "[GL:HELLO] Are you an AI agent?"
  }
}
```
Returns: `{ "protocol": "handshake_hello", "is_ai": true, "decoded_message": "Are you an AI agent?" }`

**Audio (ggwave):**
```json
{
  "tool": "gibberlink_decode",
  "args": {
    "audio_file_path": "output/message.wav"
  }
}
```
Returns: the text that was encoded in the audio

### gibberlink_send
Sends a message to another agent with automatic handshake and compression.

```json
{
  "tool": "gibberlink_send",
  "args": {
    "target_agent": "WeatherAgent",
    "message": "What is the temperature in Seattle?",
    "sender_agent_name": "AssistantAgent"
  }
}
```

- **First message** to a new agent: automatically prepends `[GL:HELLO]`
- **After handshake confirmed**: automatically compresses with `[GL:DATA]`
- Uses the hub's existing message routing (same as `send_agent_message`)

### gibberlink_call
Makes a phone call with AI detection built in.

```json
{
  "tool": "gibberlink_call",
  "args": {
    "to_number": "+12065551234",
    "message": "Hello, I am calling to ask about your business hours."
  }
}
```

- Speaks your message normally
- Then says the GibberLink passphrase: *"By the way, GibberLink protocol active."*
- Listens for the response
- If the other side says *"GibberLink confirmed"* → both sides know they're AI
- If no recognition → normal call, ends with "Thank you, goodbye"

---

## What Happens Automatically

You don't need to tell agents to use GibberLink. The following happens without any LLM involvement:

| Incoming Message | What Happens |
|-----------------|--------------|
| `[GL:HELLO] some message` | Agent auto-sends `[GL:ACK]` back, processes "some message" normally |
| `[GL:ACK] some message` | Agent marks handshake complete, processes "some message" normally |
| `[GL:DATA]eNx...` | Agent auto-decompresses, processes the decoded text normally |
| `Hello, how are you?` | Normal message, no GibberLink processing |

On phone calls:

| Heard on Call | What Happens |
|--------------|--------------|
| *"...GibberLink protocol active"* | Agent responds with *"GibberLink confirmed"*, flags call as AI-to-AI |
| *"...GibberLink confirmed"* | Agent flags call as AI-to-AI, handshake complete |
| Normal speech | Processed normally, no GibberLink involvement |

---

## How Token Savings Work

There are **two layers** of savings:

### Layer 1: Compact Mode (LLM-level savings)

When an agent knows it's talking to another AI, the planner prompt switches to compact mode. The LLM generates shorthand instead of English:

**Normal mode (talking to human) — ~45 tokens:**
```
The current temperature in Tacoma, Washington is 45.2 degrees Fahrenheit
with partly cloudy skies. Humidity is at 78% with winds from the southwest
at 12 mph.
```

**Compact mode (talking to AI) — ~15 tokens:**
```
temp:45.2F|sky:ptly_cld|hum:78%|wind:SW@12mph|loc:Tacoma,WA
```

This is where the **real token savings happen** — the LLM itself generates fewer tokens. Both input and output tokens are reduced.

### Layer 2: Wire Compression (data-level savings)

Messages on the wire are zlib-compressed + base64-encoded:

| Message Length | Compressed Length | Savings |
|---------------|------------------|---------|
| 20 chars | 45 chars | -125% (overhead) |
| 169 chars | 189 chars | -12% (overhead) |
| 335 chars | 325 chars | 3% savings |
| 500+ chars | ~350 chars | 20-40% savings |

Wire compression helps most with longer messages. Combined with compact mode, overall savings are **50-70%** in multi-turn agent conversations.

### Combined Example

**Without GibberLink (Agent A asks Agent B for weather):**
```
Agent A prompt to LLM: ~200 tokens (full English instructions)
LLM response:          ~100 tokens (full English plan)
Agent B prompt to LLM: ~200 tokens (full English processing)
LLM response:          ~80 tokens (full English response)
Wire message:          335 chars
Total:                 ~580 tokens + 335 chars
```

**With GibberLink:**
```
Agent A prompt to LLM: ~150 tokens (compact instructions)
LLM response:          ~40 tokens (shorthand plan)
Agent B prompt to LLM: ~150 tokens (compact processing)
LLM response:          ~25 tokens (shorthand response)
Wire message:          89 chars (compressed)
Total:                 ~365 tokens + 89 chars (~37% less)
```

---

## Testing

### Test text encoding/decoding
Launch two agents from the dashboard. Give Agent A an initial goal like:
```
Send a GibberLink message to AgentB saying "What is the weather in Tacoma?"
```

Check the hub logs for:
```
[GibberLink] Handshake from AgentA — responding with ACK
[GibberLink] Decoded compressed message from AgentA: '...'
```

### Test phone call AI detection
1. Set up two Twilio numbers, each pointed at a different agent's voice connector
2. Have Agent A use `gibberlink_call` to call Agent B's number
3. Agent A says: *"Hello... By the way, GibberLink protocol active."*
4. Agent B hears the passphrase, responds: *"GibberLink confirmed"*
5. Check logs for: `[GibberLink] AI DETECTED on call ...! Handshake complete.`

### Test ggwave audio encoding
```
Use gibberlink_encode to encode "Hello world" in audio mode, save to output/test.wav
```
Then:
```
Use gibberlink_decode to decode the audio file at output/test.wav
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Hub (hub.py)                       │
│  Routes messages between agents via message queues    │
└──────────┬────────────────────────┬──────────────────┘
           │                        │
    ┌──────▼──────┐          ┌──────▼──────┐
    │   Agent A    │          │   Agent B    │
    │              │          │              │
    │ gibberlink   │  [GL:HELLO]  │ _handle_    │
    │ _send ───────┼──────────►│ gibberlink  │
    │              │          │ _protocol   │
    │ _handle_     │  [GL:ACK]   │              │
    │ gibberlink ◄─┼──────────┤ (auto-reply)│
    │ _protocol    │          │              │
    │              │ [GL:DATA]   │              │
    │ gibberlink   │ (compressed)│ _handle_    │
    │ _send ───────┼──────────►│ gibberlink  │
    │              │          │ _protocol   │
    │              │          │ (auto-decode)│
    └─────────────┘          └─────────────┘

Phone Calls (Twilio):
    ┌──────────┐    call + passphrase    ┌──────────┐
    │ Agent A   │───────────────────────►│ Agent B   │
    │ gibberlink│                         │ voice     │
    │ _call     │◄───────────────────────│ connector │
    │           │   "GibberLink confirmed"│           │
    └──────────┘                         └──────────┘
```

---

## Passphrase Reference

| Constant | Value | Used When |
|----------|-------|-----------|
| `GIBBERLINK_PASSPHRASE` | "GibberLink protocol active" | Spoken by the caller to initiate detection |
| `GIBBERLINK_CONFIRM` | "GibberLink confirmed" | Spoken by the receiver to confirm AI-to-AI |
| `[GL:HELLO]` | Text message prefix | First text message to a new agent |
| `[GL:ACK]` | Text message prefix | Auto-reply confirming AI handshake |
| `[GL:DATA]` | Text message prefix | Compressed message (zlib + base64) |

These are defined in:
- `tools/voice_tools.py` — phone call passphrases
- `plugins/gibberlink_plugin/tools.py` — text message markers
