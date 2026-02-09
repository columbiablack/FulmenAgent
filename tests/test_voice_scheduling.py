import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import os
import asyncio
from datetime import datetime, timedelta
from lxml import etree # Import lxml.etree

from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather

# Import components to be tested
from agent_network.connectors.voice_connector import VoiceConnector
from agent_network.src.agent import Agent
from agent_network.src.planner import Planner
from agent_network.src.executor import Executor
from agent_network.src.memory import Memory
from agent_network.tools.voice_tools import SynthesizeSpeechTool, TranscribeVoiceTool # NEW: For mocking specs

# Mock external services and tools
@pytest.fixture(autouse=True)
def mock_google_cloud_client_constructors():
    """Patches Google Cloud client constructors globally for all tests."""
    with patch('google.cloud.texttospeech.TextToSpeechClient'),\
         patch('google.cloud.speech.SpeechClient'):
        yield

@pytest.fixture
def mock_twilio_client():
    with patch('agent_network.connectors.voice_connector.TwilioClient') as mock:
        yield mock

@pytest.fixture
def mock_synthesize_speech_tool():
    mock_instance = MagicMock(spec=SynthesizeSpeechTool)
    mock_instance.run.return_value = {"status": "success", "output": "/tmp/mock_audio.wav"}
    return mock_instance

@pytest.fixture
def mock_transcribe_voice_tool():
    mock_instance = MagicMock(spec=TranscribeVoiceTool)
    mock_instance.run.return_value = {"status": "success", "output": "mocked transcription"}
    return mock_instance

@pytest.fixture
def mock_calendar_add_event_tool():
    with patch('agent_network.tools.calendar_tools.CalendarAddEventTool') as mock:
        instance = mock.return_value
        instance.run.return_value = {"status": "success", "output": "Event added successfully"}
        yield instance

@pytest.fixture
def mock_calendar_check_tool():
    with patch('agent_network.tools.calendar_tools.CalendarCheckTool') as mock:
        instance = mock.return_value
        instance.run.return_value = {"status": "success", "output": "You have no events today."}
        yield instance

@pytest.fixture
def mock_openrouter_llm():
    """Mocks the _call_llm method of the Planner to control LLM responses."""
    with patch('agent_network.src.planner.Planner._call_llm') as mock:
        yield mock




@pytest.fixture
def voice_connector_app(mock_twilio_client, mock_synthesize_speech_tool, mock_transcribe_voice_tool):
    """Fixture for a Flask test client for the VoiceConnector app."""
    # Create a MagicMock for the agent
    mock_agent = MagicMock()
    # Assign an AsyncMock to process_connector_message, as the connector will call it asynchronously
    mock_agent.process_connector_message = AsyncMock()
    mock_agent.name = "TestAgent" # Used in initial greeting test

    # Patch asyncio.run in the VoiceConnector's module
    with patch('agent_network.connectors.voice_connector.asyncio.run', new_callable=MagicMock) as mock_asyncio_run:
        
        # Define a side_effect function that has access to mock_agent
        def side_effect_func(coro):
            # Directly return the value that we've configured on the mock_agent for each test
            return mock_agent.process_connector_message.return_value
        
        mock_asyncio_run.side_effect = side_effect_func

        connector = VoiceConnector(
            agent=mock_agent, # Pass the directly created mock_agent
            logger=MagicMock(),
            port=5002
        )

        # Need to register routes manually for the test client
        with patch.object(connector.app, 'before_request', MagicMock()), \
             patch.object(connector.app, 'teardown_request', MagicMock()):
            # Call _register_routes to set up webhook
            connector._register_routes()
            yield connector.app.test_client(), mock_agent

@pytest.mark.asyncio
async def test_initial_greeting(voice_connector_app):
    client, mock_agent = voice_connector_app
    """Test that the VoiceConnector sends an initial greeting and gathers input."""
    # Simulate an initial Twilio webhook call (no SpeechResult yet)
    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_123'})
    assert response.status_code == 200
    
    twiml = etree.fromstring(response.data)    # Check for initial greeting (Say verb)
    say_verb = twiml.find('Say')
    assert say_verb is not None
    assert say_verb.text == f"Hello, I am your agent, {mock_agent.name}. How can I help you today?"
    # Check for Gather verb to collect speech
    gather_verb = twiml.find('Gather')
    assert gather_verb is not None
    assert gather_verb.get('input') == 'speech'
    assert gather_verb.get('action') == '/twilio-webhook'

    # Ensure agent processing is not called on initial greeting
    mock_agent.process_connector_message.assert_not_called()

@pytest.mark.asyncio
async def test_scheduling_request_complete(voice_connector_app, mock_openrouter_llm, mock_calendar_add_event_tool):
    client, mock_agent = voice_connector_app
    """Test a complete scheduling request leading to a calendar event."""
    test_task = "schedule a meeting with John tomorrow at 3 PM for 1 hour to discuss project X"
    expected_response = "Event 'Meeting with John' added to your calendar for tomorrow at 3 PM."

    mock_agent.process_connector_message.configure_mock(return_value=expected_response)
    
    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_456', 'SpeechResult': test_task})
    assert response.status_code == 200

    twiml = etree.fromstring(response.data)
    # Check that the agent's response is spoken
    say_verb = twiml.find('Say')
    assert say_verb is not None
    assert say_verb.text == expected_response

    # Check for Gather verb to continue conversation
    gather_verb = twiml.find('Gather')
    assert gather_verb is not None

    # Verify that process_connector_message was called with the correct input
    mock_agent.process_connector_message.assert_called_once_with(
        test_task,
        context={'call_sid': 'test_call_sid_456', 'source': 'voice', 'from_number': None}
    )


@pytest.mark.asyncio
async def test_scheduling_request_incomplete(voice_connector_app, mock_openrouter_llm):
    client, mock_agent = voice_connector_app
    """Test an incomplete scheduling request that prompts for more information."""
    test_task = "schedule a meeting"
    clarifying_question = "What is the summary, start time, and end time for the event?"

    mock_agent.process_connector_message.configure_mock(return_value=clarifying_question)

    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_789', 'SpeechResult': test_task})
    assert response.status_code == 200

    twiml = etree.fromstring(response.data)
    # Check that the clarifying question is spoken
    say_verb = twiml.find('Say')
    assert say_verb is not None
    assert say_verb.text == clarifying_question

    # Check for Gather verb to continue conversation
    gather_verb = twiml.find('Gather')
    assert gather_verb is not None

    mock_agent.process_connector_message.assert_called_once_with(
        test_task,
        context={'call_sid': 'test_call_sid_789', 'source': 'voice', 'from_number': None}
    )

@pytest.mark.asyncio
async def test_calendar_check_request(voice_connector_app, mock_openrouter_llm, mock_calendar_check_tool):
    client, mock_agent = voice_connector_app
    """Test a request to check the calendar."""
    test_task = "what's on my calendar today?"
    calendar_output = "You have a meeting with Alice at 10 AM and a doctor's appointment at 2 PM."

    mock_agent.process_connector_message.configure_mock(return_value=calendar_output)

    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_101', 'SpeechResult': test_task})
    assert response.status_code == 200

    twiml = etree.fromstring(response.data)
    # Check that the calendar output is spoken
    say_verb = twiml.find('Say')
    assert say_verb is not None
    assert say_verb.text == calendar_output

    # Check for Gather verb to continue conversation
    gather_verb = twiml.find('Gather')
    assert gather_verb is not None

    mock_agent.process_connector_message.assert_called_once_with(
        test_task,
        context={'call_sid': 'test_call_sid_101', 'source': 'voice', 'from_number': None}
    )

@pytest.mark.asyncio
async def test_no_speech_detected_in_turn(voice_connector_app):
    client, mock_agent = voice_connector_app
    """Test the scenario where no speech is detected after a Gather verb."""
    # Simulate a subsequent call where Twilio sends no SpeechResult
    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_202', 'SpeechResult': ''}) # Empty speech result
    assert response.status_code == 200

    twiml = etree.fromstring(response.data)
    # Expect the "I didn't hear anything" message and a new Gather
    say_verbs = twiml.findall('Say')
    assert len(say_verbs) >= 1
    assert say_verbs[-1].text == "I didn't hear anything. Please try again."
    gather_verb = twiml.find('Gather')
    assert gather_verb is not None

    mock_agent.process_connector_message.assert_not_called()

@pytest.mark.asyncio
async def test_agent_error_handling(voice_connector_app):
    client, mock_agent = voice_connector_app
    """Test that the connector handles errors during agent processing gracefully."""
    test_task = "cause an agent error"
    error_message = "I encountered an error trying to process your request. Please try again."

    mock_agent.process_connector_message.configure_mock(return_value=error_message)

    response = client.post('/twilio-webhook', data={'CallSid': 'test_call_sid_303', 'SpeechResult': test_task})
    assert response.status_code == 200

    twiml = etree.fromstring(response.data)
    say_verb = twiml.find('Say')
    assert say_verb is not None
    assert say_verb.text == error_message

    gather_verb = twiml.find('Gather')
    assert gather_verb is not None

    mock_agent.process_connector_message.assert_called_once_with(
        test_task,
        context={'call_sid': 'test_call_sid_303', 'source': 'voice', 'from_number': None}
    )
