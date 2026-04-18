# Hermes Agent WSL to Windows Launcher

Windows-side launcher that bridges [Hermes Agent](https://github.com/NousResearch/hermes-agent) running in WSL2 to a local [Ollama](https://ollama.com) server running on Windows.

Double-click the `.exe` (or launch it from any directory) and Hermes starts up inside WSL2, connected to Windows Ollama, with its working directory set to the folder you launched from.

## Platform

- Windows 11 with WSL2 (Ubuntu distro)
- Local Ollama install on Windows
- Hermes Agent installed inside the WSL2 distro

## What it does (pre-flight sequence)

1. Starts Windows Ollama if not running (detached, respects the `OLLAMA_MODELS` user env var).
2. Verifies WSL2 can reach Ollama at `127.0.0.1:11434` (mirrored networking or port-forward).
3. Verifies `hermes` is on PATH inside the WSL2 distro.
4. Checks that the target model is available in Ollama; auto-pulls if missing.
5. Writes Ollama provider config to `~/.hermes/.env` and `~/.hermes/config.yaml` inside WSL.
6. Launches `hermes` interactively with inherited stdio, in the launcher's current working directory (Windows path auto-translated to `/mnt/<drive>/...` via `wsl --cd`).

## Key constants

- `WSL_DISTRO = "Ubuntu"`
- `DEFAULT_MODEL = "glm-4.7-flash:latest"`
- `HERMES_LAUNCH_CMD = "hermes"` (change to `"hermes --tui"` for TUI mode)
- `OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"`

## Configuration written to WSL

- `~/.hermes/.env`: `OPENAI_BASE_URL`, `OPENAI_API_KEY=ollama`
- `~/.hermes/config.yaml`: `model.provider=custom`, `model.base_url`, `model.name`, `model.api_key`

## Usage

### Prebuilt executable

Grab `LaunchHermesAgentWSL.exe` from the [Releases](../../releases) page and run it from whichever folder you want Hermes to open in. No admin elevation required.

### From source

Requires Python 3.12+ on Windows.

```bat
python LaunchHermesAgentWSL.py
```

### Build your own `.exe`

```bat
pip install pyinstaller
pyinstaller --onefile LaunchHermesAgentWSL.py
```

## Requirements on the system

- Ollama for Windows installed at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`
- WSL2 distro named `Ubuntu` (change `WSL_DISTRO` in the script to use a different distro)
- Hermes Agent installed inside the WSL2 distro and on `PATH`
- WSL2 mirrored networking, or port forwarding for `127.0.0.1:11434`
