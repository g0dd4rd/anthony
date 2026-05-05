# Conversational Mode - User Guide

## 🎯 What's New?

The conversational version adds **dual-mode operation**:

1. **Command Mode** - Execute desktop commands (open apps, close windows, etc.)
2. **Conversation Mode** - Chat with Gemma for questions, help, explanations

## 🤖 How It Works

### Automatic Detection (Default)

By default, the system **automatically detects** your intent:

```
You: "What is Docker?"
System: [Auto-detected: conversation]
        "Docker is a containerization platform that allows..."

You: "Open Firefox"
System: [Auto-detected: command]
        [Opens Firefox]

You: "How do I install Node.js?"
System: [Auto-detected: conversation]
        "You can install Node.js by downloading from..."

You: "Close Firefox"
System: [Auto-detected: command]
        [Closes Firefox]
```

**No mode switching needed!** The system figures it out.

---

## 🔧 Manual Mode Control

If the automatic detection gets confused, you can force a mode:

### Switch to Command Mode
```
You: "Switch to command mode"
System: "Command mode activated. I'll only execute desktop commands."

[Now all inputs treated as commands]
```

### Switch to Chat Mode
```
You: "Switch to chat mode"
System: "Chat mode activated. Ask me anything!"

[Now all inputs treated as conversation]
```

### Return to Automatic
```
You: "Automatic mode"
System: "Automatic mode. I'll detect whether you want commands or conversation."

[Back to auto-detection]
```

---

## 💬 Conversation History

The system remembers your conversation context (last 10 exchanges):

```
You: "What is Python?"
System: "Python is a high-level programming language..."

You: "How do I install it?"
System: "You can install Python by..." [knows "it" = Python]

You: "What are its main features?"
System: "Python's main features include..." [still talking about Python]
```

### Clear History

Start a fresh topic:
```
You: "Clear history"
System: "Conversation history cleared."

You: "New topic"
System: "Conversation history cleared."
```

**Note:** Commands don't pollute conversation history - only chats are remembered.

---

## 📋 Examples

### Example 1: Pure Commands
```
You: "Open text editor"
System: [command] [Opens gnome-text-editor]

You: "Type hello world"
System: [command] [Types text]

You: "Close text editor"
System: [command] "The window has unsaved changes. Options: Save, Discard, Cancel. What would you like to do?"

You: "Discard"
System: [command] [Closes without saving]
```

### Example 2: Pure Conversation
```
You: "What is Kubernetes?"
System: [conversation] "Kubernetes is a container orchestration platform..."

You: "How does it compare to Docker?"
System: [conversation] "While Docker focuses on containers, Kubernetes orchestrates..."

You: "What are pods?"
System: [conversation] "Pods are the smallest deployable units in Kubernetes..."
```

### Example 3: Mixed Usage (Automatic)
```
You: "What is the best text editor for Linux?"
System: [conversation] "Popular Linux text editors include Vim, Emacs, VS Code..."

You: "Open VS Code"
System: [command] [Launches code]

You: "How do I install extensions?"
System: [conversation] "In VS Code, extensions can be installed..."

You: "Describe screen"
System: [command] "The visible applications are: VS Code, Firefox..."
```

### Example 4: Classifier Confused (Manual Override)
```
You: "How do I close Firefox?"
System: [conversation] "To close Firefox, you can click the X button, press Alt+F4..."

You: "Switch to command mode"
System: "Command mode activated."

You: "Close Firefox"
System: [command] [Closes Firefox]

You: "Automatic mode"
System: "Automatic mode."
```

---

## 🚀 Quick Start

### Run the Conversational Version

```bash
cd ~/anthony
./voice-driven-orchestrator-mcp-conversational.py
```

### Test Automatic Detection

1. **Try a question:** "What is Python?"
   - Should auto-detect as conversation
   
2. **Try a command:** "Open Firefox"
   - Should auto-detect as command

3. **Try ambiguous:** "How do I close Firefox?"
   - Might be conversation (explanation) or command (action)
   - If wrong, use "switch to command mode"

### Test Mode Switching

1. Say "switch to chat mode"
2. Ask questions - all treated as conversation
3. Say "automatic mode"
4. Back to auto-detection

---

## 🔄 Migration from Safe Version

**Old version:** `voice-driven-orchestrator-mcp-safe.py`
- Only command mode
- No conversation capability

**New version:** `voice-driven-orchestrator-mcp-conversational.py`
- ✅ All old features preserved
- ✅ Automatic command detection (works same as before)
- ⭐ NEW: Can now ask questions and chat
- ⭐ NEW: Manual mode control when needed

**Safe to switch!** All existing command functionality works identically.

---

## ⚙️ Technical Details

### How Classification Works

**Phase 1:** Intent type classifier (fast, ~0.5s)
- Determines: command vs conversation
- Uses lightweight inference (10 tokens, temp=0.1)
- Examples-based prompt for accuracy

**Phase 2:** Route to handler
- **Command:** Uses tool schema + silent orchestrator prompt
- **Conversation:** Uses friendly assistant prompt + history

### Conversation History Management

- Keeps last 20 messages (10 exchanges)
- Manual clear only (no auto-timeout)
- Commands don't add to history
- History improves context understanding

### Fallback Strategy

- If classifier uncertain → defaults to conversation (safer)
- User can always force command mode if needed
- Explicit mode beats automatic detection

---

## 🐛 Troubleshooting

### Classifier keeps getting it wrong

**Solution:** Use manual mode switching
```
You: "Switch to command mode"  # Force all inputs as commands
You: "Switch to chat mode"     # Force all inputs as conversation
```

### Conversation remembers too much

**Solution:** Clear history
```
You: "Clear history"  # Wipe conversation context
```

### "How do I..." treated as conversation instead of command

This is **expected behavior**! Phrases like:
- "How do I close Firefox?" → Conversation (asking for instructions)
- "Close Firefox" → Command (direct action)

If you want the action, use explicit command phrasing or force command mode.

---

## 🎨 Voice Commands Summary

| Command | Effect |
|---------|--------|
| `"switch to command mode"` | Force command mode |
| `"switch to chat mode"` | Force conversation mode |
| `"automatic mode"` | Auto-detect intent |
| `"clear history"` | Clear conversation history |
| `"new topic"` | Clear conversation history |

---

## 📊 Comparison

| Feature | Safe Version | Conversational Version |
|---------|--------------|------------------------|
| Desktop commands | ✅ | ✅ |
| Safe dialog handling | ✅ | ✅ |
| VAD continuous listening | ✅ | ✅ |
| Ask questions | ❌ | ⭐ **Yes** |
| Chat capability | ❌ | ⭐ **Yes** |
| Mode switching | ❌ | ⭐ **Yes** |
| Automatic detection | ❌ | ⭐ **Yes** |
| Conversation history | ❌ | ⭐ **Yes** |

---

## ✅ Ready to Use!

The conversational version is a **superset** of the safe version - everything works the same, plus you can now chat!

Try it:
```bash
cd ~/anthony
./voice-driven-orchestrator-mcp-conversational.py
```

Enjoy both command execution AND helpful conversations! 🎉
