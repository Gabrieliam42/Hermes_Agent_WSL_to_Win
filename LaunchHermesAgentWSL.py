import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import winreg
from pathlib import Path

WSL_DISTRO = "Ubuntu"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_EXE = (
    Path(os.environ.get("USERPROFILE", str(Path.home())))
    / "AppData"
    / "Local"
    / "Programs"
    / "Ollama"
    / "ollama.exe"
)
DEFAULT_MODEL = "glm-4.7-flash:latest"
HERMES_LAUNCH_CMD = "hermes"


def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_for_url(url, timeout_seconds):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if http_ok(url):
            return True
        time.sleep(1)
    return False


def get_user_env_var(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except FileNotFoundError:
        return None


def run_wsl(command, interactive=False, capture_output=False, check=False, timeout=None):
    flag = "-ic" if interactive else "-lc"
    return subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "-e", "bash", flag, command],
        capture_output=capture_output,
        text=True,
        check=check,
        timeout=timeout,
    )


def ensure_ollama():
    """Start Windows Ollama if not already running."""
    if http_ok(OLLAMA_API_URL):
        return True

    if not OLLAMA_EXE.exists():
        raise FileNotFoundError(f"Ollama not found at {OLLAMA_EXE}")

    env = os.environ.copy()
    models_dir = get_user_env_var("OLLAMA_MODELS")
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir

    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(OLLAMA_EXE), "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=env,
        creationflags=creationflags,
        close_fds=True,
    )
    return wait_for_url(OLLAMA_API_URL, 45)


def ensure_wsl_bridge():
    """Verify WSL2 can reach Windows Ollama."""
    result = run_wsl(
        "curl -fsS --max-time 8 http://127.0.0.1:11434/api/tags >/dev/null"
    )
    return result.returncode == 0


def ensure_hermes():
    """Verify Hermes Agent is installed in WSL."""
    result = run_wsl("command -v hermes >/dev/null 2>&1", capture_output=True)
    return result.returncode == 0


def ensure_model(model):
    """Check if model is available in Ollama; pull if missing."""
    try:
        with urllib.request.urlopen(OLLAMA_API_URL, timeout=5) as resp:
            data = json.loads(resp.read())
            names = [m["name"] for m in data.get("models", [])]
            base = model.split(":")[0]
            if model in names or any(n.split(":")[0] == base for n in names):
                return True
    except Exception:
        pass

    print(f"  Model {model} not found locally. Pulling...")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/pull",
        data=json.dumps({"name": model}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            for line in resp:
                try:
                    status = json.loads(line)
                    msg = status.get("status", "")
                    if msg:
                        print(f"  {msg}", end="\r", flush=True)
                except json.JSONDecodeError:
                    pass
            print()
        return True
    except Exception as exc:
        print(f"  Pull failed: {exc}")
        return False


def configure_hermes(model, ollama_url):
    """Configure Hermes Agent to use local Ollama."""
    env_cmd = (
        "mkdir -p ~/.hermes && "
        "touch ~/.hermes/.env && "
        'sed -i "/^OPENAI_BASE_URL=/d" ~/.hermes/.env && '
        'sed -i "/^OPENAI_API_KEY=/d" ~/.hermes/.env && '
        f'echo "OPENAI_BASE_URL={ollama_url}" >> ~/.hermes/.env && '
        'echo "OPENAI_API_KEY=ollama" >> ~/.hermes/.env'
    )
    run_wsl(env_cmd)

    config_cmd = (
        f'hermes config set model.provider custom 2>/dev/null; '
        f'hermes config set model.name "{model}" 2>/dev/null; '
        f'hermes config set model.base_url "{ollama_url}" 2>/dev/null; '
        f'hermes config set model.api_key ollama 2>/dev/null; '
        "true"
    )
    run_wsl(config_cmd, interactive=True, capture_output=True)


def launch_hermes(ollama_url):
    """Launch Hermes Agent interactively in WSL2, in the caller's cwd."""
    cwd = os.getcwd()
    cmd = (
        f'export OPENAI_BASE_URL="{ollama_url}" && '
        f'export OPENAI_API_KEY="ollama" && '
        f"{HERMES_LAUNCH_CMD}"
    )
    return subprocess.run(
        ["wsl", "-d", WSL_DISTRO, "--cd", cwd, "-e", "bash", "-lc", cmd]
    )


def main():
    if os.name != "nt":
        raise RuntimeError("This launcher must be run on Windows.")

    model = DEFAULT_MODEL

    print("Checking Windows Ollama...")
    if not ensure_ollama():
        raise RuntimeError("Ollama did not start within 45 seconds.")

    print("Checking WSL bridge to Ollama...")
    if not ensure_wsl_bridge():
        raise RuntimeError(
            "WSL cannot reach Windows Ollama at http://127.0.0.1:11434.\n"
            "Enable mirrored networking in .wslconfig or configure port forwarding."
        )

    print("Checking Hermes Agent in WSL...")
    if not ensure_hermes():
        raise RuntimeError(
            f"Hermes Agent not found in WSL ({WSL_DISTRO}). Install with:\n"
            "  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/"
            "main/scripts/install.sh | bash"
        )

    print(f"Checking model {model}...")
    if not ensure_model(model):
        raise RuntimeError(
            f"Model {model} is not available and could not be pulled."
        )

    print("Configuring Hermes Agent for local Ollama...")
    configure_hermes(model, OLLAMA_BASE_URL)

    print(f"Launching Hermes Agent (model: {model})...\n")
    result = launch_hermes(OLLAMA_BASE_URL)
    sys.exit(result.returncode)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nLauncher interrupted.")
        sys.exit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
