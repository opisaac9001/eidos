# Pathos Subconscious Node

A standalone system that simulates the subconscious thought processes of Pathos, designed to run independently from the main Eidos AI system.

## Overview

The Subconscious Node generates continuous background thoughts and connects to the main Eidos system to:
- Retrieve external context (memories, conversations, activities)
- Send impulses and memory imprints back to the main system
- Operate as an independent "subconscious mind" component

## Architecture

- **Standalone System**: Runs independently on its own server/container
- **API Communication**: Connects to main Eidos system via HTTP APIs
- **Continuous Operation**: Generates thoughts in background loop
- **REST API**: Exposes endpoints for external interaction

## Components

- `api.py` - FastAPI server exposing REST endpoints
- `thinker.py` - Core thought generation loop
- `context_store.py` - Local context management
- `mood.py` - Mood tracking and management
- `detectors.py` - Impulse and memory imprint detection
- `utils.py` - LLM utilities and helper functions
- `config.json` - Configuration settings

## Setup

### Prerequisites

- Python 3.8+
- Access to an LLM server (llama.cpp, vLLM, etc.)
- Network access to main Eidos system (if running)

### Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure settings:**
   Edit `config.json` to set:
   - LLM server URL (`llm_settings.llama_cpp_server_url`)
   - Main Eidos system URL (`eidos_api_base_url`)
   - Thought generation settings
   - Mood parameters

3. **Setup wildcards (optional):**
   Ensure wildcard files are available at the path specified in `wildcard_folder_path`

## Running

### Option 1: Full System (Recommended)
```bash
# Runs both thinker and API server
./run_full.sh
```

### Option 2: Individual Components
```bash
# API server only (port 8000)
./run.sh
# or: python3 api.py

# Thinking loop only
./run_thinker.sh  
# or: python3 thinker.py
```

### Option 3: Direct Python
```bash
# Start API server
python3 api.py

# Start thinking loop (in separate terminal)
python3 thinker.py
```

## API Endpoints

The subconscious node exposes a REST API on port 8000:

- `GET /` - Health check
- `GET /docs` - API documentation
- `GET /current_thoughts` - Get recent thoughts and mood
- `POST /inject/conversation` - Inject conversation context
- `POST /inject/action` - Inject action context
- `POST /v1/pathos/impulse` - Receive impulse notifications
- `POST /v1/pathos/memory/imprint` - Receive memory imprints

## Configuration

Key settings in `config.json`:

```json
{
  "llm_settings": {
    "llama_cpp_server_url": "http://localhost:8081/v1/chat/completions",
    "temperature": 0.7
  },
  "eidos_api_base_url": "http://100.89.52.89:8080",
  "monologue_loop_settings": {
    "sleep_duration_seconds": 30,
    "max_monologue_buffer_thoughts": 100
  }
}
```

## Integration with Main Eidos System

The subconscious node is designed to work with the main Eidos system:

1. **Context Retrieval**: Fetches memories, conversations, and system state
2. **Impulse Sending**: Sends detected impulses to main system
3. **Memory Imprints**: Sends significant realizations to main system
4. **Independent Operation**: Continues working even if main system is offline

## Deployment

Since this is a standalone system, it can be deployed:

- On a separate server/VM
- In a Docker container
- In an LXC container
- On the same machine as main Eidos (different ports)

## Troubleshooting

- **Import Errors**: The system uses flexible imports to work both standalone and as part of a package
- **LLM Connection**: Check `llama_cpp_server_url` in config.json
- **Main System Connection**: Verify `eidos_api_base_url` is reachable
- **Port Conflicts**: Default API port is 8000, change in api.py if needed

## Development

The subconscious node can be developed and tested independently of the main Eidos system. It will use fallback context when the main system is unavailable.
