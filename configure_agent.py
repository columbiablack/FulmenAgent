import os
import sys
from dotenv import load_dotenv, set_key
import logging
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text

# Add the project root to the sys.path to allow importing agent_network modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_network.src.planner import Planner

# Configure logging for the script
# We'll use rich's console for output, so disable default logging to stdout
logging.basicConfig(level=logging.WARNING) 
logger = logging.getLogger(__name__)

console = Console()

DOTENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')

def get_user_input_rich(prompt_text: str, default: str = None) -> str:
    """Helper to get user input using rich.prompt.Prompt."""
    try:
        return Prompt.ask(prompt_text, default=default, console=console)
    except EOFError:
        console.print(f"[bold yellow]Warning:[/bold yellow] Non-interactive environment detected. Using default value for '{prompt_text}'.")
        return default if default is not None else "" # Return empty string if no default

def configure_agent_cli():
    console.print(Panel(
        Text("Agent Configuration Wizard", justify="center", style="bold magenta") +
        Text("\nThis wizard will guide you through setting up your agent's name, OpenRouter API key, and preferred model.", justify="center") +
        Text("\nPress Ctrl+C at any time to exit.", justify="center", style="dim"),
        title="[bold blue]Welcome[/bold blue]",
        border_style="green"
    ))

    # Load existing .env variables to pre-fill defaults
    load_dotenv(DOTENV_PATH)

    

    # 2. OpenRouter API Key
    current_api_key = os.getenv("OPENROUTER_API_KEY", "")
    api_key = get_user_input_rich(f"[bold cyan]Enter your OpenRouter API Key (sk-...)[/bold cyan]", current_api_key)
    set_key(DOTENV_PATH, "OPENROUTER_API_KEY", api_key)
    console.print("[green]OpenRouter API Key saved.[/green]")

    # Temporarily set the API key in the environment for model fetching
    os.environ["OPENROUTER_API_KEY"] = api_key

    # 3. Select OpenRouter Model
    planner = Planner()
    if not api_key:
        console.print("[bold yellow]OpenRouter API Key not provided. Skipping model selection.[/bold yellow]")
        set_key(DOTENV_PATH, "OPENROUTER_MODEL", "")
    else:
        console.print("[bold blue]Fetching available free models from OpenRouter...[/bold blue]")
        free_models = planner.get_available_models(free_only=True)

        if not free_models:
            console.print("[bold yellow]No free models found or an error occurred. You can manually set OPENROUTER_MODEL later.[/bold yellow]")
            set_key(DOTENV_PATH, "OPENROUTER_MODEL", "")
        else:
            console.print(Panel(
                Text("Available Free OpenRouter Models", justify="center", style="bold underline blue"),
                border_style="blue"
            ))
            for i, model in enumerate(free_models):
                console.print(f"[magenta]{i+1}.[/magenta] ID: [bold]{model['id']}[/bold], Name: {model['name']}")
            
            selected_model_id = None
            while selected_model_id is None:
                try:
                    choice = get_user_input_rich("[bold cyan]Enter the number of the model you want to use[/bold cyan]")
                    choice_index = int(choice) - 1
                    if 0 <= choice_index < len(free_models):
                        selected_model_id = free_models[choice_index]['id']
                    else:
                        console.print("[bold red]Invalid choice. Please enter a number from the list.[/bold red]")
                except ValueError:
                    console.print("[bold red]Invalid input. Please enter a number.[/bold red]")
            
            set_key(DOTENV_PATH, "OPENROUTER_MODEL", selected_model_id)
            console.print(f"[green]OpenRouter model set to: [bold]{selected_model_id}[/bold][/green]")

    # 4. Ollama Configuration
    console.print(Panel(
        Text("Ollama Server Configuration", justify="center", style="bold blue") +
        Text("\nIf you want to use a local Ollama server for LLM inference, configure its base URL here.", justify="center"),
        title="[bold blue]Ollama Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_ollama = Prompt.ask("[bold cyan]Do you want to configure a local Ollama server?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_ollama:
        current_ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_base_url = get_user_input_rich(f"[bold cyan]Enter your Ollama server's base URL (e.g., http://localhost:11434)[/bold cyan]", current_ollama_base_url)
        set_key(DOTENV_PATH, "OLLAMA_BASE_URL", ollama_base_url)
        console.print(f"[green]Ollama Base URL set to: [bold]{ollama_base_url}[/bold][/green]")
    else:
        console.print("[yellow]Ollama server configuration skipped.[/yellow]")
        set_key(DOTENV_PATH, "OLLAMA_BASE_URL", "") # Ensure it's cleared if not used

    # 5. Moonshot AI (Kimi) Configuration
    console.print(Panel(
        Text("Moonshot AI (Kimi) Configuration", justify="center", style="bold blue") +
        Text("\nIf you want to use Moonshot AI models (Kimi), configure your API key and preferred model here.", justify="center"),
        title="[bold blue]Kimi Setup[/bold blue]",
        border_style="blue"
    ))

    use_kimi = Prompt.ask("[bold cyan]Do you want to configure Moonshot AI (Kimi) models?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_kimi:
        current_moonshot_api_key = os.getenv("MOONSHOT_API_KEY", "")
        moonshot_api_key = get_user_input_rich(f"[bold cyan]Enter your Moonshot AI API Key (sk-...)[/bold cyan]", current_moonshot_api_key, password=True)
        set_key(DOTENV_PATH, "MOONSHOT_API_KEY", moonshot_api_key)
        console.print("[green]Moonshot AI API Key saved.[/green]")

        # Temporarily set the API key in the environment for model fetching
        os.environ["MOONSHOT_API_KEY"] = moonshot_api_key

        # 4. Select Kimi Model
        planner = Planner() # Re-initialize planner to pick up Moonshot API key
        if not moonshot_api_key:
            console.print("[bold yellow]Moonshot AI API Key not provided. Skipping model selection.[/bold yellow]")
            set_key(DOTENV_PATH, "MOONSHOT_MODEL", "")
        else:
            console.print("[bold blue]Fetching available Kimi models from Moonshot AI...[/bold blue]")
            kimi_models = planner._get_available_moonshot_models() # Use the new private method

            if not kimi_models:
                console.print("[bold yellow]No Kimi models found or an error occurred. You can manually set MOONSHOT_MODEL later.[/bold yellow]")
                set_key(DOTENV_PATH, "MOONSHOT_MODEL", "")
            else:
                console.print(Panel(
                    Text("Available Kimi Models", justify="center", style="bold underline blue"),
                    border_style="blue"
                ))
                for i, model in enumerate(kimi_models):
                    console.print(f"[magenta]{i+1}.[/magenta] ID: [bold]{model['id']}[/bold], Name: {model['name']}")
                
                selected_model_id = None
                while selected_model_id is None:
                    try:
                        choice = get_user_input_rich("[bold cyan]Enter the number of the Kimi model you want to use[/bold cyan]")
                        choice_index = int(choice) - 1
                        if 0 <= choice_index < len(kimi_models):
                            selected_model_id = kimi_models[choice_index]['id']
                        else:
                            console.print("[bold red]Invalid choice. Please enter a number from the list.[/bold red]")
                    except ValueError:
                        console.print("[bold red]Invalid input. Please enter a number.[/bold red]")
                
                set_key(DOTENV_PATH, "MOONSHOT_MODEL", selected_model_id)
                console.print(f"[green]Moonshot AI model set to: [bold]{selected_model_id}[/bold][/green]")
    else:
        console.print("[yellow]Moonshot AI (Kimi) configuration skipped.[/yellow]")
        set_key(DOTENV_PATH, "MOONSHOT_API_KEY", "") # Ensure it's cleared if not used
        set_key(DOTENV_PATH, "MOONSHOT_MODEL", "") # Ensure it's cleared if not used

    # 6. Connector Configurations (Discord)
    console.print(Panel(
        Text("Discord Connector Configuration", justify="center", style="bold blue") +
        Text("\nConfigure settings for your Discord bot. If you don't plan to use Discord, you can skip this.", justify="center"),
        title="[bold blue]Discord Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_discord = Prompt.ask("[bold cyan]Do you want to configure a Discord connector?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_discord:
        agent_name_for_creds = get_user_input_rich("[bold cyan]Enter the agent name that will use this Discord connector (e.g., MyDiscordAgent)[/bold cyan]", "MyDiscordAgent").upper()

        current_discord_token = os.getenv(f"{agent_name_for_creds}_DISCORD_TOKEN", "")
        discord_token = get_user_input_rich(f"[bold cyan]Enter Discord Bot Token for {agent_name_for_creds}[/bold cyan]", current_discord_token)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_DISCORD_TOKEN", discord_token)
        console.print(f"[green]Discord Token for {agent_name_for_creds} saved.[/green]")

        current_discord_channel_id = os.getenv(f"{agent_name_for_creds}_DISCORD_CHANNEL_ID", "")
        discord_channel_id = get_user_input_rich(f"[bold cyan]Enter Discord Channel ID for {agent_name_for_creds}[/bold cyan]", current_discord_channel_id)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_DISCORD_CHANNEL_ID", discord_channel_id)
        console.print(f"[green]Discord Channel ID for {agent_name_for_creds} saved.[/green]")
    else:
        console.print("[yellow]Discord connector configuration skipped.[/yellow]")
        
    # 5. Telegram Connector Configuration
    console.print(Panel(
        Text("Telegram Connector Configuration", justify="center", style="bold blue") +
        Text("\nConfigure settings for your Telegram bot. If you don't plan to use Telegram, you can skip this.", justify="center"),
        title="[bold blue]Telegram Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_telegram = Prompt.ask("[bold cyan]Do you want to configure a Telegram connector?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_telegram:
        agent_name_for_creds = get_user_input_rich("[bold cyan]Enter the agent name that will use this Telegram connector (e.g., MyTelegramAgent)[/bold cyan]", "MyTelegramAgent").upper()

        current_telegram_token = os.getenv(f"{agent_name_for_creds}_TELEGRAM_TOKEN", "")
        telegram_token = get_user_input_rich(f"[bold cyan]Enter Telegram Bot Token for {agent_name_for_creds}[/bold cyan]", current_telegram_token)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_TELEGRAM_TOKEN", telegram_token)
        console.print(f"[green]Telegram Token for {agent_name_for_creds} saved.[/green]")

        current_telegram_allowed_chats = os.getenv(f"{agent_name_for_creds}_TELEGRAM_ALLOWED_CHATS", "")
        telegram_allowed_chats = get_user_input_rich(f"[bold cyan]Enter comma-separated Telegram Allowed Chat IDs for {agent_name_for_creds} (optional)[/bold cyan]", current_telegram_allowed_chats)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_TELEGRAM_ALLOWED_CHATS", telegram_allowed_chats)
        console.print(f"[green]Telegram Allowed Chat IDs for {agent_name_for_creds} saved.[/green]")
    else:
        console.print("[yellow]Telegram connector configuration skipped.[/yellow]")

    # 6. LINE Connector Configuration
    console.print(Panel(
        Text("LINE Connector Configuration", justify="center", style="bold blue") +
        Text("\nConfigure settings for your LINE bot. If you don't plan to use LINE, you can skip this.", justify="center"),
        title="[bold blue]LINE Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_line = Prompt.ask("[bold cyan]Do you want to configure a LINE connector?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_line:
        agent_name_for_creds = get_user_input_rich("[bold cyan]Enter the agent name that will use this LINE connector (e.g., MyLineAgent)[/bold cyan]", "MyLineAgent").upper()

        current_line_channel_secret = os.getenv(f"{agent_name_for_creds}_LINE_CHANNEL_SECRET", "")
        line_channel_secret = get_user_input_rich(f"[bold cyan]Enter LINE Channel Secret for {agent_name_for_creds}[/bold cyan]", current_line_channel_secret, password=True)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_LINE_CHANNEL_SECRET", line_channel_secret)
        console.print(f"[green]LINE Channel Secret for {agent_name_for_creds} saved.[/green]")

        current_line_channel_access_token = os.getenv(f"{agent_name_for_creds}_LINE_CHANNEL_ACCESS_TOKEN", "")
        line_channel_access_token = get_user_input_rich(f"[bold cyan]Enter LINE Channel Access Token for {agent_name_for_creds}[/bold cyan]", current_line_channel_access_token, password=True)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_LINE_CHANNEL_ACCESS_TOKEN", line_channel_access_token)
        console.print(f"[green]LINE Channel Access Token for {agent_name_for_creds} saved.[/green]")
    else:
        console.print("[yellow]LINE connector configuration skipped.[/yellow]")
        
    # 7. WhatsApp Connector Configuration
    console.print(Panel(
        Text("WhatsApp Connector Configuration (Requires WhatsApp Business API setup)", justify="center", style="bold blue") +
        Text("\nConfigure settings for your WhatsApp Business API integration. If you don't plan to use WhatsApp, you can skip this.", justify="center"),
        title="[bold blue]WhatsApp Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_whatsapp = Prompt.ask("[bold cyan]Do you want to configure a WhatsApp connector?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_whatsapp:
        agent_name_for_creds = get_user_input_rich("[bold cyan]Enter the agent name that will use this WhatsApp connector (e.g., MyWhatsappAgent)[/bold cyan]", "MyWhatsappAgent").upper()

        current_whatsapp_phone_id = os.getenv(f"{agent_name_for_creds}_WHATSAPP_PHONE_NUMBER_ID", "")
        whatsapp_phone_id = get_user_input_rich(f"[bold cyan]Enter WhatsApp Phone Number ID for {agent_name_for_creds}[/bold cyan]", current_whatsapp_phone_id)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_WHATSAPP_PHONE_NUMBER_ID", whatsapp_phone_id)
        console.print(f"[green]WhatsApp Phone Number ID for {agent_name_for_creds} saved.[/green]")

        current_whatsapp_access_token = os.getenv(f"{agent_name_for_creds}_WHATSAPP_ACCESS_TOKEN", "")
        whatsapp_access_token = get_user_input_rich(f"[bold cyan]Enter WhatsApp Access Token for {agent_name_for_creds}[/bold cyan]", current_whatsapp_access_token)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_WHATSAPP_ACCESS_TOKEN", whatsapp_access_token)
        console.print(f"[green]WhatsApp Access Token for {agent_name_for_creds} saved.[/green]")
    else:
        console.print("[yellow]WhatsApp connector configuration skipped.[/yellow]")
        
    # 7. X (Twitter) Connector Configuration
    console.print(Panel(
        Text("X (formerly Twitter) Connector Configuration", justify="center", style="bold blue") +
        Text("\nConfigure settings for your X API integration. If you don't plan to use X, you can skip this.", justify="center"),
        title="[bold blue]X Setup[/bold blue]",
        border_style="blue"
    ))
    
    use_x = Prompt.ask("[bold cyan]Do you want to configure an X (Twitter) connector?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_x:
        agent_name_for_creds = get_user_input_rich("[bold cyan]Enter the agent name that will use this X connector (e.g., MyXAgent)[/bold cyan]", "MyXAgent").upper()

        current_x_consumer_key = os.getenv(f"{agent_name_for_creds}_X_CONSUMER_KEY", "")
        x_consumer_key = get_user_input_rich(f"[bold cyan]Enter X Consumer Key for {agent_name_for_creds}[/bold cyan]", current_x_consumer_key)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_X_CONSUMER_KEY", x_consumer_key)
        console.print(f"[green]X Consumer Key for {agent_name_for_creds} saved.[/green]")

        current_x_consumer_secret = os.getenv(f"{agent_name_for_creds}_X_CONSUMER_SECRET", "")
        x_consumer_secret = get_user_input_rich(f"[bold cyan]Enter X Consumer Secret for {agent_name_for_creds}[/bold cyan]", current_x_consumer_secret)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_X_CONSUMER_SECRET", x_consumer_secret)
        console.print(f"[green]X Consumer Secret for {agent_name_for_creds} saved.[/green]")

        current_x_access_token = os.getenv(f"{agent_name_for_creds}_X_ACCESS_TOKEN", "")
        x_access_token = get_user_input_rich(f"[bold cyan]Enter X Access Token for {agent_name_for_creds}[/bold cyan]", current_x_access_token)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_X_ACCESS_TOKEN", x_access_token)
        console.print(f"[green]X Access Token for {agent_name_for_creds} saved.[/green]")

        current_x_access_token_secret = os.getenv(f"{agent_name_for_creds}_X_ACCESS_TOKEN_SECRET", "")
        x_access_token_secret = get_user_input_rich(f"[bold cyan]Enter X Access Token Secret for {agent_name_for_creds}[/bold cyan]", current_x_access_token_secret)
        set_key(DOTENV_PATH, f"{agent_name_for_creds}_X_ACCESS_TOKEN_SECRET", x_access_token_secret)
        console.print(f"[green]X Access Token Secret for {agent_name_for_creds} saved.[/green]")
    else:
        console.print("[yellow]X (Twitter) connector configuration skipped.[/yellow]")
        
    # 8. Email API Preferences
    console.print(Panel(
        Text("Email API Preferences", justify="center", style="bold blue") +
        Text("\nThis section helps define which email service your agent should be configured to interact with.", justify="center"),
        title="[bold blue]Email API Setup[/bold blue]",
        border_style="blue"
    ))

    email_service = get_user_input_rich("[bold cyan]Which email service do you plan to use (e.g., Gmail, Outlook, None)?[/bold cyan]", os.getenv("EMAIL_API_SERVICE", "None"))
    set_key(DOTENV_PATH, "EMAIL_API_SERVICE", email_service)
    if email_service.lower() != "none":
        email_auth_method = get_user_input_rich(f"[bold cyan]What authentication method for {email_service} (e.g., OAuth, API Key, App Password)?[/bold cyan]", os.getenv("EMAIL_API_AUTH_METHOD", "OAuth"))
        set_key(DOTENV_PATH, "EMAIL_API_AUTH_METHOD", email_auth_method)
        console.print(f"[green]Email API service set to: [bold]{email_service}[/bold] with auth method: [bold]{email_auth_method}[/bold][/green]")
    else:
        console.print("[yellow]Email API configuration skipped.[/yellow]")


    # 9. Calendar API Preferences
    console.print(Panel(
        Text("Calendar API Preferences", justify="center", style="bold blue") +
        Text("\nThis section helps define which calendar service your agent should be configured to interact with.", justify="center"),
        title="[bold blue]Calendar API Setup[/bold blue]",
        border_style="blue"
    ))

    calendar_service = get_user_input_rich("[bold cyan]Which calendar service do you plan to use (e.g., Google Calendar, Outlook Calendar, None)?[/bold cyan]", os.getenv("CALENDAR_API_SERVICE", "None"))
    set_key(DOTENV_PATH, "CALENDAR_API_SERVICE", calendar_service)
    if calendar_service.lower() != "none":
        calendar_auth_method = get_user_input_rich(f"[bold cyan]What authentication method for {calendar_service} (e.g., OAuth, API Key)?[/bold cyan]", os.getenv("CALENDAR_API_AUTH_METHOD", "OAuth"))
        set_key(DOTENV_PATH, "CALENDAR_API_AUTH_METHOD", calendar_auth_method)
        console.print(f"[green]Calendar API service set to: [bold]{calendar_service}[/bold] with auth method: [bold]{calendar_auth_method}[/bold][/green]")
    else:
        console.print("[yellow]Calendar API configuration skipped.[/yellow]")
        
    # 10. Google Cloud API Preferences (for Voice Tools)
    console.print(Panel(
        Text("Google Cloud API Preferences (for Text-to-Speech and Speech-to-Text)", justify="center", style="bold blue") +
        Text("\nThis section configures access to Google Cloud services for voice capabilities.", justify="center") +
        Text("\nRequires a Google Cloud Project with Text-to-Speech API and Speech-to-Text API enabled.", justify="center") +
        Text("\nYou'll need a service account key file (JSON) downloaded from your Google Cloud Console.", justify="center") +
        Text("\nMore info: https://cloud.google.com/docs/authentication/getting-started", justify="center", style="dim"),
        title="[bold blue]Google Cloud Setup[/bold blue]",
        border_style="blue"
    ))

    use_google_cloud_voice = Prompt.ask("[bold cyan]Do you plan to use Google Cloud for voice capabilities (Text-to-Speech, Speech-to-Text)?[/bold cyan]", choices=["yes", "no"], default="no", console=console).lower() == "yes"
    if use_google_cloud_voice:
        current_gac_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        gac_path = get_user_input_rich(f"[bold cyan]Enter the ABSOLUTE path to your Google Cloud Service Account JSON key file[/bold cyan]", current_gac_path)
        set_key(DOTENV_PATH, "GOOGLE_APPLICATION_CREDENTIALS", gac_path)
        console.print(f"[green]Google Application Credentials path saved: [bold]{gac_path}[/bold][/green]")
    else:
        console.print("[yellow]Google Cloud voice capabilities configuration skipped.[/yellow]")
        
    # 11. VoIP API Preferences (for Phone Calls)
    console.print(Panel(
        Text("VoIP API Preferences (for Phone Calls)", justify="center", style="bold blue") +
        Text("\nThis section helps define which VoIP service your agent should be configured to use for real phone calls.", justify="center") +
        Text("\nNOTE: Actual outbound calls to PSTN numbers usually incur costs.", justify="center", style="dim yellow"),
        title="[bold blue]VoIP API Setup[/bold blue]",
        border_style="blue"
    ))

    voip_service = get_user_input_rich("[bold cyan]Which VoIP service do you plan to use (e.g., Twilio, FreePBX/Asterisk (internal), None)?[/bold cyan]", os.getenv("VOIP_API_SERVICE", "None"))
    set_key(DOTENV_PATH, "VOIP_API_SERVICE", voip_service)
    if voip_service.lower() != "none":
        voip_auth_method = get_user_input_rich(f"[bold cyan]What authentication method for {voip_service} (e.g., Account SID/Auth Token, SIP Trunk details)?[/bold cyan]", os.getenv("VOIP_API_AUTH_METHOD", "API Keys"))
        set_key(DOTENV_PATH, "VOIP_API_AUTH_METHOD", voip_auth_method)
        
        # Specific prompts for Twilio, if chosen
        if voip_service.lower() == "twilio":
            twilio_sid = get_user_input_rich("[bold cyan]Enter Twilio Account SID:[/bold cyan]", os.getenv("TWILIO_ACCOUNT_SID", ""))
            set_key(DOTENV_PATH, "TWILIO_ACCOUNT_SID", twilio_sid)
            twilio_auth_token = get_user_input_rich("[bold cyan]Enter Twilio Auth Token:[/bold cyan]", os.getenv("TWILIO_AUTH_TOKEN", ""))
            set_key(DOTENV_PATH, "TWILIO_AUTH_TOKEN", twilio_auth_token)
            twilio_phone_number = get_user_input_rich("[bold cyan]Enter Twilio Phone Number (e.g., +15017122661):[/bold cyan]", os.getenv("TWILIO_PHONE_NUMBER", ""))
            set_key(DOTENV_PATH, "TWILIO_PHONE_NUMBER", twilio_phone_number)
            console.print("[green]Twilio credentials saved.[/green]")
        
        # Specific prompts for FreePBX/Asterisk, if chosen
        elif voip_service.lower() in ["freepbx", "asterisk"]:
            freepbx_host = get_user_input_rich("[bold cyan]Enter FreePBX/Asterisk Host (e.g., 192.168.1.100):[/bold cyan]", os.getenv("FREEPBX_HOST", ""))
            set_key(DOTENV_PATH, "FREEPBX_HOST", freepbx_host)
            freepbx_ami_user = get_user_input_rich("[bold cyan]Enter Asterisk AMI Username:[/bold cyan]", os.getenv("FREEPBX_AMI_USER", ""))
            set_key(DOTENV_PATH, "FREEPBX_AMI_USER", freepbx_ami_user)
            freepbx_ami_secret = get_user_input_rich("[bold cyan]Enter Asterisk AMI Secret:[/bold cyan]", os.getenv("FREEPBX_AMI_SECRET", ""), password=True)
            set_key(DOTENV_PATH, "FREEPBX_AMI_SECRET", freepbx_ami_secret)
            console.print("[green]FreePBX/Asterisk AMI credentials saved.[/green]")
        
        console.print(f"[green]VoIP API service set to: [bold]{voip_service}[/bold] with auth method: [bold]{voip_auth_method}[/bold][/green]")
    else:
        console.print("[yellow]VoIP API configuration skipped.[/yellow]")
        
    # 12. Hub URL Configuration
    
    current_hub_url = os.getenv("HUB_URL", "http://127.0.0.1:5000")
    hub_url = get_user_input_rich(f"[bold cyan]Enter the Hub URL (e.g., http://127.0.0.1:5000 or your remote hub's address)[/bold cyan]", current_hub_url)
    set_key(DOTENV_PATH, "HUB_URL", hub_url)
    console.print(f"[green]Hub URL set to: [bold]{hub_url}[/bold][/green]")

    console.print(Panel(
        Text("Configuration complete! Your settings have been saved to .env", justify="center", style="bold green") +
        Text("\nYou can now start your agent network using 'python main_agent_entrypoint.py'.", justify="center"),
        title="[bold green]Success![/bold green]",
        border_style="green"
    ))

if __name__ == "__main__":
    try:
        configure_agent_cli()
    except KeyboardInterrupt:
        console.print("\n[bold red]Configuration cancelled by user.[/bold red]")