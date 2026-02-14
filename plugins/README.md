# Agent Network Plugins

This directory is where you can add custom plugins to extend the functionality of your Agent Network. Plugins allow you to introduce new tools that your agents can utilize to perform tasks, interact with external services, or execute custom logic.

## How Plugins Work

Each plugin should reside in its own sub-directory within the `plugins/` folder. The core components of a plugin are:

1.  **Plugin Folder:** A directory (e.g., `my_custom_plugin/`) containing all plugin files.
2.  **`manifest.json`:** A JSON file describing the plugin's metadata and its entry point.
3.  **`tools.py` (or similar):** A Python file containing the implementation of your custom tools.
4.  **`requirements.txt` (optional):** A file listing any Python dependencies specific to your plugin.

## 1. Creating a Plugin

### Plugin Structure

A typical plugin structure looks like this:

```
plugins/
└── my_example_plugin/
    ├── manifest.json
    ├── tools.py
    └── requirements.txt  (optional)
```

### `manifest.json`

This file provides metadata about your plugin and tells the Agent Network how to load your tools.

```json
{
  "name": "My Example Plugin",
  "version": "1.0.0",
  "description": "A brief description of what your plugin does.",
  "author": "Your Name/Organization",
  "entry_point": "tools:get_tools"
}
```

*   `name`: A human-readable name for your plugin.
*   `version`: The version of your plugin.
*   `description`: A short explanation of the plugin's purpose.
*   `author`: The author(s) of the plugin.
*   `entry_point`: Specifies the Python module and function to call to retrieve your plugin's tools. Format: `module_name:function_name`. (e.g., `"tools:get_tools"` means call the `get_tools()` function in `tools.py`).

### `tools.py` (Implementing Your Tools)

Your tools must inherit from `agent_network.tools.base_tool.BaseTool`.

```python
# plugins/my_example_plugin/tools.py
import logging
from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

class MyCustomTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="my_custom_tool_name",
            description="A concise description of what this tool does and its arguments."
        )

    def run(self, arg1: str, arg2: int):
        """
        Executes the custom tool's functionality.
        All arguments should be passed as keyword arguments.
        """
        logger.info(f"[MyCustomTool]: Executing with {arg1} and {arg2}")
        # Your custom logic here
        result = f"Processed '{arg1}' {arg2} times."
        return {"status": "success", "output": result}

def get_tools():
    """
    This function is the entry point specified in manifest.json.
    It should return a list of initialized BaseTool instances provided by this plugin.
    """
    return [MyCustomTool()]

```

### `requirements.txt` (Optional)

If your plugin requires external Python libraries, list them in a `requirements.txt` file within your plugin's directory.

```
# plugins/my_example_plugin/requirements.txt
requests>=2.25.1
beautifulsoup4
```

## 2. Installing a Plugin

There are two primary ways to install a plugin:

### A. Manual Installation

1.  **Create Plugin Folder:** Place your plugin's directory (e.g., `my_example_plugin/`) inside the main `plugins/` directory of your Agent Network installation.
2.  **Install Dependencies (if any):** If your plugin has a `requirements.txt`, you will need to install its dependencies. The Agent Network will log a warning if auto-install is disabled. You can manually install them by navigating to your project root and running:
    ```bash
    pip install -r plugins/my_example_plugin/requirements.txt
    ```
    Or, if auto-install is enabled in the dashboard, the agent will attempt to install them on startup.
3.  **Restart Agents:** Restart all running agents and the hub for the new plugin to be discovered and its tools to become available.

### B. Via Dashboard Upload (Recommended)

1.  **Package Your Plugin:** Create a `.zip` archive of your plugin's directory (e.g., `my_example_plugin.zip`). The `.zip` file should directly contain your plugin's folder, or its contents, including `manifest.json`.
2.  **Navigate to Dashboard:** Open your Agent Network Dashboard in a web browser.
3.  **Go to "Plugin Management":** Click on the "Plugin Management" tab.
4.  **Upload:** Use the "Upload New Plugin (.zip)" form to select and upload your `.zip` file.
5.  **Restart Agents:** After a successful upload, you will need to restart your agents for the new plugin to be discovered and its tools to become available. If "Auto-install Plugin Dependencies" is enabled, its dependencies will be installed automatically during agent startup.

## 3. Managing Plugins from the Dashboard

The "Plugin Management" tab on the dashboard provides several features:

*   **Plugin List:** Shows all plugins discovered by active agents, including their name, description, version, author, and current status (Enabled/Disabled).
*   **Toggle On/Off:** Each plugin has a toggle switch.
    *   **Enabled:** The agent will attempt to load this plugin and its tools on startup.
    *   **Disabled:** The agent will skip loading this plugin.
    *   **Important:** Changes to a plugin's enabled/disabled status only take effect after the associated agents are **restarted**.
*   **Auto-install Plugin Dependencies Toggle:** This global setting determines whether agents automatically execute `pip install -r <plugin_path>/requirements.txt` on startup for discovered plugins.
    *   **Enabled:** (Default) Agents will attempt to install dependencies automatically.
    *   **Disabled:** Agents will skip automatic dependency installation and log a warning if a plugin has a `requirements.txt`.
*   **Remove Button:** Clicking "Remove" will delete the plugin's directory from the `plugins/` folder.
    *   **Important:** This operation **does NOT automatically uninstall any Python dependencies** that the plugin might have installed. You would need to manually uninstall those if desired, keeping in mind that other plugins or the core application might still depend on them.
    *   After removing a plugin, restart your agents to fully unregister its tools.

## Example: My Weather Plugin

The `my_weather_plugin` serves as a functional example of how to build and integrate a plugin. It provides a `weather_tool` that can fetch real-time weather data.

*   **`plugins/my_weather_plugin/manifest.json`**: Describes the weather plugin.
*   **`plugins/my_weather_plugin/tools.py`**: Contains the `WeatherTool` class, inheriting from `BaseTool`, and the `get_tools()` entry point.
*   **`plugins/my_weather_plugin/requirements.txt`**: Lists `geopy` as a dependency. When auto-install is enabled, `geopy` will be installed automatically.

To use the `weather_tool`, ensure the plugin is enabled and an agent is running. You can then prompt the agent with queries like:
*   "What is the current temperature in London?"
*   "Give me the temperature forecast for New York for tomorrow."
*   "What was the UV index in Sydney?"
