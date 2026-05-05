import asyncio
import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_agent():
    # 1. Tell the client how to launch your MCP Server
    server_params = StdioServerParameters(
        command="python3",
        args=["mcp_server.py"] # Point this to your server file
    )

    # 2. Connect to the MCP server via stdio
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 3. Ask the MCP server what tools it has
            mcp_tools_response = await session.list_tools()
            
            # 4. Format the MCP tools into the format Ollama expects
            ollama_tools = []
            for tool in mcp_tools_response.tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })

            print(f"[!] Loaded {len(ollama_tools)} tools from MCP Server.")

            # 5. Prompt the Model!
            user_prompt = "Start calculator"
            print(f"\nUser: {user_prompt}")
            
            response = ollama.chat(
                model='llama3.2', # Or whichever model you downloaded
                messages=[{'role': 'user', 'content': user_prompt}],
                tools=ollama_tools
            )

            # 6. Execute the Tool if the LLM requested it
            if response['message'].get('tool_calls'):
                for tool_call in response['message']['tool_calls']:
                    tool_name = tool_call['function']['name']
                    tool_args = tool_call['function']['arguments']
                    
                    print(f"[!] Model wants to run: {tool_name}({tool_args})")
                    
                    # Send the command back to the MCP server to execute on the desktop
                    result = await session.call_tool(tool_name, tool_args)
                    print(f"[!] Result from Desktop: {result.content[0].text}")
            else:
                # If no tools were needed, print the normal text response
                print(f"Agent: {response['message']['content']}")

if __name__ == "__main__":
    asyncio.run(run_agent())
