# Voice & Phone Tools Setup Guide

This guide walks you through setting up the Twilio-powered voice and phone tools so your agents can make calls, send SMS, and receive inbound phone calls.

---

## What You Get

| Tool | What It Does |
|------|-------------|
| `make_phone_call` | Calls a phone number and speaks a message |
| `send_sms` | Sends an SMS text message |
| `check_call_status` | Checks the status of a call by its Call SID |
| `cold_call` | Runs a scripted outbound call to a contact |
| `synthesize_speech` | Converts text to audio (MP3) using Edge TTS (free) |
| `transcribe_voice` | Transcribes a WAV audio file to text (requires Google Cloud) |

---

## Step 1: Create a Twilio Account

1. Go to [https://www.twilio.com/try-twilio](https://www.twilio.com/try-twilio) and sign up
2. Verify your email and phone number
3. Twilio gives you a free trial with credits (~$15) to test with

### Get Your Credentials

From the [Twilio Console](https://console.twilio.com/):

- **Account SID** — shown on the main dashboard (starts with `AC`)
- **Auth Token** — click "Show" next to it on the dashboard

### Get a Phone Number

1. In the Twilio Console, go to **Phone Numbers > Manage > Buy a number**
2. Pick a number (local numbers are cheapest, ~$1.15/month)
3. Make sure it has **Voice** and **SMS** capabilities checked
4. Copy the number in E.164 format (e.g. `+12065551234`)

> **Trial Account Limits:** On a free trial, you can only call/text numbers you've verified in the Twilio console. Go to **Phone Numbers > Manage > Verified Caller IDs** to add numbers.

---

## Step 2: Configure in the Dashboard

1. Open the Dashboard at `http://127.0.0.1:5000`
2. Go to the **Admin Settings** tab
3. Scroll down to **Voice / Phone (Twilio) Configuration**
4. Fill in:
   - **Enable Voice/Phone Tools** — check the box
   - **Twilio Account SID** — paste your Account SID
   - **Twilio Auth Token** — paste your Auth Token
   - **Twilio Phone Number** — paste your number (e.g. `+12065551234`)
5. Click **Save Configuration**
6. **Restart the hub** for changes to take effect

### Or Configure via .env

Edit `/root/agent/.env` directly:

```
ENABLE_VOICE_TOOLS='yes'
TWILIO_ACCOUNT_SID='ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
TWILIO_AUTH_TOKEN='your_auth_token_here'
TWILIO_PHONE_NUMBER='+12065551234'
```

---

## Step 3: Test It

### Launch an Agent

From the Dashboard, create a new agent with an initial goal like:

```
Send an SMS to +1XXXXXXXXXX saying "Hello from the agent network!"
```

Or for a phone call:

```
Call +1XXXXXXXXXX and tell them the current weather forecast
```

The agent will use the `send_sms` or `make_phone_call` tool automatically.

---

## Step 4: Inbound Calls (Optional)

If you want people to call your Twilio number and talk to the agent:

### 4a. Launch Agent with Voice Connector

In the Dashboard, when adding a new agent:
- Set **Connector Type** to **Voice**

This starts a webhook server on port 5002.

### 4b. Expose the Webhook Publicly

The Twilio servers need to reach your webhook. Options:

**Option A: ngrok (easiest for testing)**
```bash
# Install ngrok: https://ngrok.com/download
ngrok http 5002
```
This gives you a public URL like `https://abc123.ngrok.io`.

**Option B: Direct port forwarding**
If your server has a public IP, forward port 5002 (or use a reverse proxy like nginx).

### 4c. Configure Twilio Webhook

1. Go to the [Twilio Console](https://console.twilio.com/) > **Phone Numbers** > click your number
2. Under **Voice Configuration**:
   - Set **"A call comes in"** to **Webhook**
   - Enter your URL: `https://YOUR_PUBLIC_URL:5002/twilio-webhook`
   - Method: **POST**
3. Click **Save**

Now when someone calls your Twilio number, the agent will answer, greet them, listen to their speech, process it, and respond.

---

## Tool Usage Examples

### make_phone_call
```json
{
  "tool": "make_phone_call",
  "args": {
    "to_number": "+12065551234",
    "message": "Hello! This is your AI agent calling to remind you about your meeting at 3pm."
  }
}
```

Optional args: `voice` (default: `alice`), `language` (default: `en-US`)

### send_sms
```json
{
  "tool": "send_sms",
  "args": {
    "to_number": "+12065551234",
    "message": "Your package has been delivered!"
  }
}
```

### check_call_status
```json
{
  "tool": "check_call_status",
  "args": {
    "call_sid": "CA1234567890abcdef"
  }
}
```

### cold_call
```json
{
  "tool": "cold_call",
  "args": {
    "phone_number": "+12065551234",
    "call_script": "Hi, this is a call from the sales team. We have a special offer for you today.",
    "contact_name": "John Smith"
  }
}
```

### synthesize_speech
```json
{
  "tool": "synthesize_speech",
  "args": {
    "text": "Hello world, this is a test.",
    "output_file_path": "output/greeting.mp3"
  }
}
```

Optional args: `voice` (default: `en-US-JennyNeural`), `rate`, `volume`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Twilio credentials not configured" | Make sure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set and the hub was restarted |
| "TWILIO_PHONE_NUMBER not configured" | Add your Twilio phone number in Admin Settings |
| Calls fail with "not verified" | On trial accounts, you can only call numbers added to Verified Caller IDs in Twilio Console |
| Agent doesn't load voice tools | Check that ENABLE_VOICE_TOOLS is set to 'yes' and restart the hub |
| Inbound calls don't reach the agent | Make sure port 5002 is accessible and the Twilio webhook URL is correct |
| "edge_tts package not installed" | Run `pip install edge-tts` |
| "twilio package not installed" | Run `pip install twilio` |

---

## Costs

| Action | Approximate Cost |
|--------|-----------------|
| Twilio phone number | ~$1.15/month |
| Outbound call | ~$0.014/min (US) |
| Outbound SMS | ~$0.0079/message (US) |
| Inbound call | ~$0.0085/min (US) |
| Inbound SMS | ~$0.0075/message (US) |
| Edge TTS (synthesize_speech) | Free |
| Twilio trial credits | ~$15 free |

Prices vary by country. See [Twilio Pricing](https://www.twilio.com/pricing) for details.
