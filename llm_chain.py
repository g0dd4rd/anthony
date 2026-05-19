import json
import subprocess
import time

from utils import log_and_print
import utils

from app_index import smart_match_window, get_friendly_app_name

logger = utils.logger

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_mcp_client = None
_call_llama_server = None
_speak = None
_check_automation_health = None
_DEBUG = False


def init(mcp_client, call_llama_server_fn, speak_fn, check_health_fn, debug=False):
    global _mcp_client, _call_llama_server, _speak
    global _check_automation_health, _DEBUG
    _mcp_client = mcp_client
    _call_llama_server = call_llama_server_fn
    _speak = speak_fn
    _check_automation_health = check_health_fn
    _DEBUG = debug


def run_chain(command_messages, filtered_tools, available_tools, direct_mcp_tools,
              response_start_time):
    """
    Run the agentic LLM tool-calling loop.

    Calls the LLM, processes tool_calls, chains results back,
    and speaks the final answer. Mutates command_messages in place.
    """
    MAX_CHAIN_STEPS = 5
    last_tool_result = None
    chain_abort = False

    for chain_step in range(MAX_CHAIN_STEPS):
        if chain_step > 0:
            log_and_print(f"[CHAIN] Step {chain_step + 1}/{MAX_CHAIN_STEPS}")

        debug_lines = ["[DEBUG] Messages sent to LLM:"]
        for msg in command_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if content and len(content) > 200:
                content = content[:200] + "..."
            debug_lines.append(f"  [{role}]: {content}")
        debug_lines.append(f"[DEBUG] Available tools: {[t['function']['name'] for t in filtered_tools]}")
        log_and_print('\n'.join(debug_lines), level='debug', console=_DEBUG)

        logger.info(f"[LLM_REQ] chain_step={chain_step} tools={[t['function']['name'] for t in filtered_tools]} msg_count={len(command_messages)}")
        max_tokens = 300
        llm_start_time = time.time()
        response = _call_llama_server(
            messages=command_messages,
            tools=filtered_tools,
            temperature=0.0,
            max_tokens=max_tokens
        )
        llm_elapsed = time.time() - llm_start_time

        # Detect truncation: if LLM hit max_tokens, retry with more
        eval_count = response.get('eval_count', 0)
        if eval_count >= max_tokens and response['message'].get('tool_calls'):
            log_and_print(f"[LLM] Output truncated at {max_tokens} tokens, retrying with 600...", level='warning')
            response = _call_llama_server(
                messages=command_messages,
                tools=filtered_tools,
                temperature=0.0,
                max_tokens=600
            )
            retry_elapsed = time.time() - llm_start_time - llm_elapsed
            llm_elapsed = time.time() - llm_start_time
            log_and_print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s (incl. truncation retry: {retry_elapsed:.2f}s)")
        else:
            log_and_print(f"[TIMING] ⏱️  LLM inference took: {llm_elapsed:.2f}s")

        logger.info(f"[LLM_RESP] inference={llm_elapsed:.2f}s tokens={response.get('eval_count', 'N/A')} has_tool_calls={bool(response['message'].get('tool_calls'))}")

        debug_lines = [f"[DEBUG] Gemma eval_count: {response.get('eval_count', 'N/A')} tokens"]
        debug_lines.append(f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}")
        if response['message'].get('content'):
            debug_lines.append(f"[DEBUG] Content preview: {response['message']['content'][:200]}")
        if response['message'].get('tool_calls'):
            debug_lines.append("[DEBUG] Tool calls:")
            for tc in response['message']['tool_calls']:
                debug_lines.append(f"  - {tc['function']['name']}: {tc['function']['arguments']}")
        log_and_print('\n'.join(debug_lines), level='debug', console=_DEBUG)

        message = response['message']
        command_messages.append(message)

        if not message.get('tool_calls'):
            content = message.get('content', '').strip()
            if content:
                log_and_print(f"\n[OS Feedback]: {content}")
                response_time = time.time() - response_start_time
                log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                _speak(content)
            elif last_tool_result:
                log_and_print(f"\n[OS Feedback]: {last_tool_result}")
                response_time = time.time() - response_start_time
                log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                _speak(last_tool_result)
            else:
                log_and_print("[COMMAND] ⚠️  No tool call generated. Try rephrasing or switch to chat mode.", level='warning')
                response_time = time.time() - response_start_time
                log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
                _speak("I'm not sure what command to run. Try rephrasing or say 'switch to chat mode'.")
            break

        for tool_call in message['tool_calls']:
            tool_name = tool_call['function']['name']
            arguments = tool_call['function']['arguments']
            tool_call_id = tool_call.get('id', f"call_{chain_step}_{tool_name}")

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    log_and_print(f"[COMMAND] ⚠️  LLM returned malformed JSON for {tool_name}: {arguments[:100]}...", level='warning')
                    _speak("Something went wrong processing that command. Please try again.")
                    chain_abort = True
                    break

            result = None

            if tool_name in direct_mcp_tools:
                log_and_print(f"\n[SYSTEM] Calling MCP tool directly: {tool_name}")

                if tool_name == "gnome_search" and "query" in arguments:
                    query = arguments["query"].strip()

                    if query.endswith(' website'):
                        url = query[:-8].strip()
                        if not url.startswith('http://') and not url.startswith('https://'):
                            url = f"https://www.{url}"
                        log_and_print(f"[GNOME_SEARCH] Detected website marker, opening URL via xdg-open: {url}")
                        subprocess.run(['xdg-open', url], check=False,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        result = f"Opening {url} in browser"

                    elif query.endswith(' file'):
                        filename = query[:-5].strip()
                        log_and_print(f"[GNOME_SEARCH] Detected file marker, using open_file: {filename}")
                        result = _mcp_client.call_tool("open_file", {"path": filename})

                    else:
                        try:
                            win_list = json.loads(_mcp_client.call_tool("list_windows", {}))
                            match = smart_match_window(query, win_list)
                            if match:
                                _mcp_client.call_tool("focus_window", {"id": match["id"]})
                                friendly = get_friendly_app_name(match.get('wmClass', query))
                                result = f"{friendly} is already running. Switched to it."
                                log_and_print(f"[GNOME_SEARCH] App already running: {friendly}, focused window '{match.get('title', '')}'")
                            else:
                                result = _mcp_client.call_tool(tool_name, arguments)
                        except Exception:
                            result = _mcp_client.call_tool(tool_name, arguments)
                else:
                    result = _mcp_client.call_tool(tool_name, arguments)

                if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                    log_and_print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                    health_ok, health_msg = _check_automation_health(auto_enable=True)
                    if health_ok:
                        log_and_print(f"[SYSTEM] Retrying {tool_name}...")
                        result = _mcp_client.call_tool(tool_name, arguments)
                    else:
                        result = f"Error: {health_msg}"

            elif tool_name in available_tools:
                function_to_call = available_tools[tool_name]
                result = function_to_call(**arguments)

                if "Error" in result and ("disabled" in result.lower() or "not responding" in result.lower()):
                    log_and_print(f"[SYSTEM] Tool failed, attempting auto-recovery...")
                    health_ok, health_msg = _check_automation_health(auto_enable=True)
                    if health_ok:
                        log_and_print(f"[SYSTEM] Retrying {tool_name}...")
                        result = function_to_call(**arguments)
                    else:
                        result = f"Error: {health_msg}"

            else:
                result = f"Unknown tool: {tool_name}"
                log_and_print(f"[COMMAND] ⚠️  {result}", level='warning')

            log_and_print(f"\n[OS Feedback]: {result}")
            logger.info(f"[TOOL_EXEC] tool={tool_name} args={arguments} result_len={len(str(result))}")
            logger.debug(f"[TOOL_RESULT] tool={tool_name} result={str(result)[:500]}")
            last_tool_result = result

            command_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": str(result)
            })

        if chain_abort:
            break

    else:
        log_and_print(f"[CHAIN] ⚠️  Reached max chain steps ({MAX_CHAIN_STEPS})", level='warning')
        if last_tool_result:
            response_time = time.time() - response_start_time
            log_and_print(f"[TIMING] ⏱️  Response time: {response_time:.2f}s")
            _speak(last_tool_result)

    response_time = time.time() - response_start_time
    log_and_print(f"[TIMING] ⏱️  Total chain time: {response_time:.2f}s")
