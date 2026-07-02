from utils import log_and_print

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_call_llama_server = None
_debug = False


def init(call_llama_server_fn, debug=False):
    global _call_llama_server, _debug
    _call_llama_server = call_llama_server_fn
    _debug = debug


def classify_intent_type(user_input: str) -> str:
    """Classify if user input is a desktop command or conversational chat.

    Returns: 'command' or 'conversation'
    """
    from config.prompts import CLASSIFIER_PROMPT

    classifier_prompt = CLASSIFIER_PROMPT.format(user_input=user_input)

    try:
        response = _call_llama_server(
            messages=[{"role": "user", "content": classifier_prompt}],
            temperature=0.1,
            max_tokens=10,
        )

        result = response["message"]["content"].strip().lower()

        if "command" in result:
            return "command"
        elif "conversation" in result:
            return "conversation"
        else:
            log_and_print(
                f"[CLASSIFIER] Unclear result: '{result}', defaulting to conversation",
                level="warning",
            )
            return "conversation"

    except Exception as e:
        log_and_print(f"[CLASSIFIER] Error: {e}, defaulting to conversation")
        return "conversation"


def handle_conversation(user_input: str, conversation_history: list) -> tuple:
    """Handle conversational chat.

    Args:
        user_input: User's question/chat
        conversation_history: List of previous message dicts

    Returns:
        (answer_text, updated_history)
    """
    from config.prompts import CONVERSATION_PROMPT

    messages = [{"role": "system", "content": CONVERSATION_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_input})

    try:
        log_and_print("[CHAT] Generating response...")

        debug_lines = ["[DEBUG] Conversation messages sent to LLM:"]
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            debug_lines.append(f"  [{role}]: {content}")
        log_and_print("\n".join(debug_lines), level="debug", console=_debug)

        response = _call_llama_server(messages=messages, temperature=0.7, max_tokens=500)

        log_and_print(
            f"[DEBUG] Response content length: {len(response['message'].get('content', ''))}",
            level="debug",
            console=_debug,
        )

        answer = response["message"]["content"]

        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": answer})

        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

        return answer, conversation_history

    except Exception as e:
        error_msg = f"Sorry, I encountered an error: {str(e)}"
        return error_msg, conversation_history
