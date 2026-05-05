#!/usr/bin/env python3
import subprocess
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Minimal Desktop Assistant")

# Ensure the Accessibility bus is active (suppress all output to prevent stdio corruption)
try:
    subprocess.run(
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'toolkit-accessibility', 'true'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
except Exception:
    # Write to stderr instead of print() to avoid breaking MCP JSON communication
    sys.stderr.write("Enabling ATSPI failed\n")

# --- TTS Function ---
@mcp.tool()
def speak(text: str) -> str:
    """Gives vocal feedback using the espeak-ng command line utility."""
    # Mute stdout/stderr so 'error: Host is down' doesn't pollute the terminal
    subprocess.run(
        ["espeak-ng", "-v", "en-us", "-s", "140", text], 
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False
    )
    return f"Spoke: '{text}'"

@mcp.tool()
def start_app(app_name: str) -> str:
    """Starts a given application by its command name (e.g., 'gnome-calculator')."""
    try:
        # We MUST completely daemonize the application so it survives the MCP server's death.
        # 1. nohup: Ignores the SIGHUP signal sent when the orchestrator closes the pipe.
        # 2. start_new_session=True: Moves the app into its own independent process group.
        # 3. close_fds=True: Forces the app to let go of the MCP Server's communication pipes.
        subprocess.Popen(
            ["nohup", app_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True
        )
        speak(f"The application {app_name} is running")
        return f"Successfully started {app_name}"
    except Exception as e:
        speak(f"The application {app_name} failed to start")
        return f"Failed to start {app_name}: {e}"

if __name__ == "__main__":
    # Run the server over standard input/output (stdio)
    # This is required for the local orchestrator to communicate with it
    mcp.run(transport='stdio')

