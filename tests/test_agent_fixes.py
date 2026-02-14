import pytest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the project root to the Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We need to import main_agent_entrypoint after sys.path is updated
from main_agent_entrypoint import main as main_entrypoint_function

@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """
    Fixture to mock out all external dependencies of main_agent_entrypoint.py.
    """
    mocker.patch('main_agent_entrypoint.start_hub_if_not_running')
    mocker.patch('main_agent_entrypoint.find_free_port', return_value=5001)
    mocker.patch('main_agent_entrypoint.Prompt.ask', return_value='TestAgent')
    mocker.patch('main_agent_entrypoint.get_connector_class', return_value=MagicMock())
    
    # Mock the Agent class itself
    mock_agent_instance = MagicMock()
    mock_agent_instance.name = "TestAgent"
    mocker.patch('main_agent_entrypoint.Agent', return_value=mock_agent_instance)
    
    # Mock importlib.reload for the modules it reloads
    mocker.patch('importlib.reload')

    # Mock requests.post specifically
    mocker.patch('requests.post')
    
    # Mock logger to prevent actual log output during tests if desired
    mocker.patch('main_agent_entrypoint.logger')
    mocker.patch('main_agent_entrypoint.console')
    
    # Mock main_shutdown_event.wait() to prevent blocking
    mocker.patch('main_agent_entrypoint.main_shutdown_event.wait')


def run_main_with_args(mocker, initial_goal_value):
    """
    Helper function to run the main_entrypoint_function with specific arguments.
    """
    # Create a mock for argparse.ArgumentParser.parse_args()
    mock_args = MagicMock()
    mock_args.num_agents = 1
    mock_args.agent_names = "TestAgent"
    mock_args.connector_types = "none"
    mock_args.proactive_loops = "no"
    mock_args.execution_modes = "safe"
    mock_args.batch_experience = "no"
    mock_args.proactive_interval = 600
    mock_args.initial_goal = initial_goal_value

    mocker.patch('argparse.ArgumentParser.parse_args', return_value=mock_args)
    
    # Call the main function
    main_entrypoint_function()

# --- Test Cases for Initial Goal ---

def test_initial_goal_empty_string_no_post_request(mocker):
    """
    Verifies that no POST request is sent to the hub when initial_goal is an empty string.
    """
    run_main_with_args(mocker, "")
    main_entrypoint_function()
    # Assert that requests.post was NOT called
    main_entrypoint_function.requests.post.assert_not_called()


def test_initial_goal_whitespace_only_no_post_request(mocker):
    """
    Verifies that no POST request is sent to the hub when initial_goal is only whitespace.
    """
    run_main_with_args(mocker, "   ")
    main_entrypoint_function()
    # Assert that requests.post was NOT called
    main_entrypoint_function.requests.post.assert_not_called()

def test_initial_goal_valid_string_sends_post_request(mocker):
    """
    Verifies that a POST request IS sent to the hub with correct payload
    when initial_goal is a valid string.
    """
    initial_goal = "Solve the world's problems"
    run_main_with_args(mocker, initial_goal)

    # Assert that requests.post WAS called
    main_entrypoint_function.requests.post.assert_called_once()
    
    # Check the call arguments (payload)
    args, kwargs = main_entrypoint_function.requests.post.call_args
    assert f"{main_entrypoint_function.HUB_URL}/api/user_messages" in args[0]
    assert kwargs['json']['agent_name'] == 'TestAgent' # As mocked by Prompt.ask and agent creation
    assert kwargs['json']['message'] == initial_goal
