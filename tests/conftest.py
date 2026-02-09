import sys
import os
import pytest

# Add the project's top-level directory (parent of agent_network) to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# You can add global fixtures or configurations here if needed
