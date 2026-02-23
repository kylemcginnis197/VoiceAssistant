# Voice Assistant

A speech-to-speech AI voice assistant powered by Claude. It listens for a wake word, transcribes speech with Whisper, processes requests through Claude with tool integrations, and responds with synthesized speech via Kokoro TTS.

## Features

- **Wake Word Detection** - Hands-free activation using OpenWakeWord
- **Speech-to-Text** - OpenAI Whisper for accurate transcription
- **LLM Processing** - Claude (Sonnet/Opus) with tool use and adaptive thinking
- **Text-to-Speech** - Kokoro TTS with optional RVC voice conversion
- **Smart Home Control** - Govee light control (toggle, brightness, color)
- **Spotify Integration** - Search, play, pause, skip tracks
- **Weather** - Current conditions via WeatherAPI
- **Context Management** - Automatic token compaction for long conversations

## Project Structure

```
voice_assistant/
├── main.py              # Entry point
├── audio.py             # Audio I/O, wake word, VAD, transcription
├── model.py             # Claude API client & tool management
├── speech.py            # TTS (Kokoro + optional RVC)
├── config.py            # Configuration constants
├── log.py               # Logging setup
├── prompts/
│   └── system_prompt.md # System prompt & persona
├── tools/
│   ├── tools.py         # Tool registry
│   ├── weather.py       # Weather API integration
│   ├── spotify.py       # Spotify playback control
│   └── govee/
│       ├── controller.py # Govee device control
│       └── govee_lib.py  # Govee API wrapper
```

## Setup

### Prerequisites

- Python 3.10
- PyAudio (requires PortAudio system library)
- A microphone and speaker

### Installation

```bash
python -m venv venv_py310
source venv_py310/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your-anthropic-api-key

# Tools (optional)
GOVEE_API_KEY=your-govee-api-key
WEATHER_API=your-weatherapi-key
SPOTIPY_CLIENT_ID=your-spotify-client-id
SPOTIPY_CLIENT_SECRET=your-spotify-client-secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### Run

```bash
python main.py
```

## Configuration

Key settings in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `AI_MODEL` | `sonnet 4.6` | Claude model to use |
| `TTS_VOICE` | `am_puck` | Kokoro voice ID |
| `TTS_SPEED` | `1.0` | Speech speed multiplier |
| `VAD_SPEECH_THRESHOLD` | `0.65` | Voice activity detection sensitivity |
| `CONVERSATION_TIMEOUT` | `10` | Seconds of silence before exiting conversation |
| `RVC_ENABLE` | `False` | Enable RVC voice conversion |

## How It Works

1. **Wake word** - Listens continuously until the activation phrase is detected
2. **Record** - Captures speech until 0.5s of silence (using Silero VAD)
3. **Transcribe** - Whisper converts audio to text
4. **Process** - Claude processes the request, optionally calling tools
5. **Speak** - Kokoro TTS synthesizes the response and plays it back
6. **Loop** - Returns to listening for the next command or wake word
