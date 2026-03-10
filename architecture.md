Voice-Driven Desktop Agent: Architecture DiagramsThe following diagrams illustrate the exact flow of data from the user's voice, through the AI orchestration layer, down to the GNOME desktop via the Model Context Protocol (MCP), and back to the user.1. Component Architecture FlowchartThis graph shows the structural relationship between the hardware, the Orchestrator, the AI models, and the Red Hat QE automation tools.graph TD
    User((User))
    
    subgraph "I/O Layer (Hardware)"
        Mic[Microphone]
        Speaker[Speakers]
    end
    
    subgraph "AI Core Layer"
        STT[STT Engine<br/>e.g., Whisper]
        LLM[LLM / Decision Engine<br/>e.g., Llama-3]
        VLM[VLM / Vision<br/>e.g., LLaVA]
        TTS[TTS Engine<br/>e.g., Piper]
    end
    
    subgraph "Orchestration Layer"
        Orch{Master Orchestrator}
    end
    
    subgraph "Tooling Layer"
        MCP[GNOME MCP Server]
    end
    
    subgraph "Desktop Layer (Wayland/GNOME)"
        Dogtail[Dogtail / qecore<br/>UI Interaction]
        Ponytail[Ponytail<br/>Silent Screenshots]
    end

    %% Flow of Data
    User -- Speaks --> Mic
    Orch -. Checks Prerequisites & Inits .- Mic
    Mic -- Audio Stream --> Orch
    
    Orch -- Audio --> STT
    STT -- Transcript --> Orch
    
    Orch -- Text + MCP Schemas --> LLM
    
    LLM -- Action / Tool Request --> MCP
    
    MCP -- Inject Clicks/Keys --> Dogtail
    MCP -- Request Pixels --> Ponytail
    
    Ponytail -- Image File --> VLM
    VLM -- Image Analysis --> MCP
    
    Dogtail -- Success/Fail Status --> MCP
    
    MCP -- Tool Result Context --> LLM
    LLM -- Final Text Response --> Orch
    
    Orch -- Text --> TTS
    TTS -- Audio --> Speaker
    Speaker -- Listens --> User
2. Interaction Sequence DiagramThis sequence diagram maps the timeline of a complex user request (e.g., "What's on my screen? If Calculator is open, click 7."), demonstrating how the Orchestrator hands off tasks between models and the desktop.sequenceDiagram
    actor User
    participant Orch as Master Orchestrator
    participant STT as STT Engine
    participant LLM as LLM
    participant MCP as GNOME MCP Server
    participant Desk as Desktop (Dogtail/Ponytail)
    participant VLM as VLM
    participant TTS as TTS Engine

    Note over Orch: Step 1: Init (Mic check, Boot Models, Load MCP)
    
    User->>Orch: "What's on my screen? Click 7." (Spoken)
    Orch->>STT: Send raw audio
    STT-->>Orch: "What's on my screen? Click 7." (Text)
    
    Orch->>LLM: Pass text + available MCP Tools
    
    Note over LLM, MCP: Step 2: Fulfill Vision Requirement
    LLM->>MCP: Call Tool: get_screen_context()
    MCP->>Desk: Trigger Ponytail screenshot
    Desk-->>MCP: Saved to /tmp/screen.png
    MCP->>VLM: Analyze /tmp/screen.png
    VLM-->>MCP: "Calculator is open."
    MCP-->>LLM: Tool Result: "Calculator is open."
    
    Note over LLM, MCP: Step 3: Fulfill Action Requirement
    LLM->>MCP: Call Tool: click_ui_element('Calculator', '7')
    MCP->>Desk: Trigger Dogtail AT-SPI click
    Desk-->>MCP: Action successful
    MCP-->>LLM: Tool Result: "Clicked 7 successfully."
    
    Note over LLM, Orch: Step 4: Finalize & Respond
    LLM-->>Orch: "I see the Calculator is open, and I have clicked 7 for you."
    
    Orch->>TTS: Send text for speech synthesis
    TTS-->>User: (Audio output) "I see the Calculator is open..."
Key Takeaways from this Flow:The Orchestrator is purely a Manager: It doesn't make decisions or parse UI logic. It simply moves strings and audio between modules.The LLM is the Director: It sits in a loop with the MCP server until it has satisfied the user's prompt (e.g., fetching an image, asking the VLM for a description, and then deciding to click a button based on that description).The MCP Server isolates the complexity: Neither the Orchestrator nor the LLM needs to know what Wayland, AT-SPI, or qecore are. They just interact with a clean JSON API provided by the MCP Server.

