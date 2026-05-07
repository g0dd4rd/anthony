# Presentation Mode Guide

## Problem
When presenting online with screen recording/streaming, you need to:
- Talk to your audience (using headset/default audio)
- Give commands to the orchestrator (without it triggering on presentation audio)
- Avoid audio device conflicts with recording software (Kooha)

## Solution: Push-to-Talk Mode

### Quick Start

**For presentations, run:**
```bash
./voice-driven-orchestrator-mcp-llama-server.py --ptt
```

**For normal use:**
```bash
./voice-driven-orchestrator-mcp-llama-server.py
```

### How It Works

#### Push-to-Talk Mode (--ptt):
1. Orchestrator starts but **does NOT listen** automatically
2. You see: `🎤 Press ENTER to speak (Ctrl+C to exit):`
3. When ready to give a command:
   - Press **ENTER**
   - Speak your command
   - Orchestrator processes it
   - Returns to waiting state
4. No accidental triggers on presentation audio! 🎉

#### Normal Mode (no --ptt):
- Continuous VAD listening (auto-detects speech)
- Good for hands-free operation
- Not ideal for presentations (triggers on all audio)

### Presentation Setup Example

#### Scenario: Online Demo with Screen Recording

**Audio Setup:**
- **Headset/Default**: For talking to audience
- **Laptop Mic**: Ready for orchestrator commands (only when ENTER pressed)

**Screen Recording (Kooha):**
1. Start Kooha screen recording
2. Configure audio: Headset microphone for narration
3. Start recording

**Orchestrator:**
1. Start in PTT mode: `./voice-driven-orchestrator-mcp-llama-server.py --ptt`
2. During presentation:
   - Talk normally to audience (headset mic)
   - When you want to demo a command:
     - Press ENTER
     - Give voice command to orchestrator
     - Continues your demo seamlessly

**No conflicts!** Kooha uses headset, orchestrator only listens when you press ENTER.

### Visual Feedback

**PTT Mode Start:**
```
============================================================
💬  CONVERSATIONAL Agentic OS - PUSH-TO-TALK MODE
============================================================
✅ VAD - unlimited voice input
✅ Safe close - never loses data without your consent
✅ Dialog detection - reads options to you
✅ Voice confirmation - you choose what to do
⭐ Conversation mode - ask questions, get help
⭐ Automatic detection - seamlessly switches modes
🎤 PUSH-TO-TALK - Press ENTER to speak

Mode switching:
  • 'switch to command mode' - force command mode
  • 'switch to chat mode' - force conversation mode
  • 'automatic mode' - auto-detect intent
  • 'clear history' - clear conversation history

💡 Tip: PTT mode prevents accidental triggering during presentations

============================================================
🎤 PUSH-TO-TALK MODE ACTIVE
============================================================
Press ENTER to speak a command
Press Ctrl+C to exit

🎤 Press ENTER to speak (Ctrl+C to exit):
```

**After Pressing ENTER:**
```
[PTT] 🟢 Listening activated...
🎤 [VAD] Listening...
🔴 Recording...
⏹️  Processing...
✅ You said: "Take a screenshot"

[MODE] 🤖 Auto-detected: command
...
[OS Feedback]: Full desktop screenshot saved to ...

[PTT] Ready for next command

🎤 Press ENTER to speak (Ctrl+C to exit):
```

### Tips for Smooth Presentations

1. **Practice the flow** before live demo:
   - Get comfortable with ENTER → speak → wait pattern
   - Know which commands you'll demo

2. **Keep commands short and clear:**
   - "Screenshot"
   - "List windows"
   - "Close Firefox"

3. **Have a backup plan:**
   - If VAD doesn't detect speech: Press ENTER again
   - If command fails: Rephrase and try again
   - Normal mode available as fallback

4. **Minimize audio interference:**
   - Mute presentation audio during voice commands
   - Or pause before pressing ENTER

5. **Visual cues for audience:**
   - Mention "I'm going to give it a voice command now"
   - Press ENTER (visible on screen if showing terminal)
   - Speak clearly

### Comparison

| Feature | Normal Mode | PTT Mode (--ptt) |
|---------|-------------|------------------|
| **Listening** | Continuous (VAD) | Only after ENTER |
| **Presentations** | ❌ Triggers on all audio | ✅ Only when you want |
| **Device conflicts** | ⚠️ Possible | ✅ None |
| **Hands-free** | ✅ Yes | ❌ Need to press key |
| **Control** | Auto-detect speech | Manual trigger |
| **Best for** | Solo use | Demos, presentations |

### Troubleshooting

**Q: PTT mode doesn't listen after ENTER?**
- Check if mic is working: Test in normal mode first
- Ensure laptop mic is accessible (not blocked by Kooha)

**Q: Still triggers during presentation?**
- You're in normal mode! Exit and restart with `--ptt`

**Q: Want to switch mid-session?**
- Can't switch modes dynamically
- Exit (Ctrl+C) and restart with/without --ptt

**Q: Forgot which mode I'm in?**
- PTT shows: `🎤 PUSH-TO-TALK MODE ACTIVE` banner
- PTT prompts: `🎤 Press ENTER to speak`
- Normal mode: No ENTER prompt, just listens

### Example Presentation Script

```bash
# Terminal 1: Start llama-server (do this BEFORE presentation)
./start_llama_server.sh

# Terminal 2: Start orchestrator in PTT mode
./voice-driven-orchestrator-mcp-llama-server.py --ptt

# Terminal 3: Your presentation notes / Kooha recording

# During presentation:
# [Talk to audience normally]
# "Now I'll demonstrate voice control..."
# [Press ENTER in Terminal 2]
# [Speak command]
# "Take a screenshot"
# [Wait for result]
# [Continue presentation]
```

### Performance

PTT mode has **identical performance** to normal mode:
- Same ~2× speedup with llama-server + Vulkan GPU
- Same command latency (~8-12s)
- Only difference: Waits for ENTER before listening

---

## Summary

✅ **Use --ptt for presentations** to avoid accidental triggering  
✅ **No audio device conflicts** with recording software  
✅ **Clear control** over when to listen  
✅ **Same performance** as normal mode  

Perfect for demos, screen recordings, and online presentations! 🎬
