"""
setup_wizard.py - Interactive first-time setup.

Guides the user through:
1. Checking Python and Chrome
2. Validating API keys
3. Getting NotebookLM URL
4. Setting up config.json
5. Testing everything works
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from api_manager import APIValidator, print_validation_report, build_providers_from_validation

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def press_enter():
    input("\nPress ENTER to continue...")


def ask_yes_no(question: str, default=True) -> bool:
    prompt = "[Y/n]" if default else "[y/N]"
    while True:
        ans = input(f"\n{question} {prompt}: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        if not ans:
            return default
        print("Please answer y or n.")


def ask_input(question: str, default="", required=False) -> str:
    while True:
        prompt = f"{question}"
        if default:
            prompt += f" (default: {default})"
        ans = input(f"\n{prompt}: ").strip()
        if not ans:
            if default:
                return default
            if required:
                print("This field is required.")
                continue
            return ""
        return ans


def check_python():
    """Verify Python version."""
    ver = sys.version_info
    if ver.major < 3 or (ver.major == 3 and ver.minor < 11):
        print(
            f"\n❌ Python {ver.major}.{ver.minor} is too old. Need Python 3.11+\n"
            f"Download from: https://www.python.org/downloads/"
        )
        sys.exit(1)
    print(f"\n✓ Python {ver.major}.{ver.minor}.{ver.micro} OK")


def check_chrome():
    """Verify Chrome is installed."""
    paths_to_check = [
        Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in paths_to_check:
        if p.exists():
            print(f"\n✓ Chrome found at {p}")
            return True

    print(
        "\n⚠️  Chrome not found. NotebookLM feature won't work.\n"
        "Install Chrome from: https://www.google.com/chrome/"
    )
    return ask_yes_no("Continue without NotebookLM?", default=False)


def validate_apis():
    """Test all available API keys."""
    print("\n" + "="*70)
    print("CHECKING API KEYS...")
    print("="*70)
    print(
        "\nThis checks if your API keys are valid and suggests free alternatives.\n"
        "Environment variables: GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY"
    )

    validator = APIValidator()
    results = validator.validate_all()
    working, failed, missing = print_validation_report(results)

    if not working:
        print(
            "\n❌ No working API keys found.\n"
            "You need at least one of:\n"
            "  1. Gemini API (https://ai.google.dev/)\n"
            "  2. Groq API (https://console.groq.com)\n"
            "  3. OpenRouter (https://openrouter.ai)\n"
            "  4. Ollama running locally (https://ollama.ai)\n"
        )
        setup_api = ask_yes_no("\nWould you like help getting a free API key?", default=True)
        if setup_api:
            print_api_setup_guide(results)
            press_enter()
            # Try again
            validator = APIValidator()
            results = validator.validate_all()
            working, failed, missing = print_validation_report(results)

        if not working:
            print("\n❌ Cannot continue without at least one working API key.")
            sys.exit(1)

    return results


def print_api_setup_guide(results: dict):
    """Print setup instructions for free APIs."""
    print(
        "\n" + "="*70
        "\nFREE API SETUP GUIDE (pick ONE)\n"
        "="*70
    )

    print(
        "\n1️⃣  GROQ (FASTEST & EASIEST)\n"
        "   - Go to: https://console.groq.com\n"
        "   - Sign up (1 min)\n"
        "   - Copy your API key\n"
        "   - Set environment variable (Windows Command Prompt, run as Admin):\n"
        '        setx GROQ_API_KEY "<paste-your-key>"\n'
        "   - Restart this app\n"
    )

    print(
        "\n2️⃣  GEMINI (GOOGLE)\n"
        "   - Go to: https://ai.google.dev/\n"
        "   - Click 'Get API Key'\n"
        "   - Create new key (enable billing first)\n"
        "   - Copy your API key\n"
        "   - Set environment variable (Windows Command Prompt, run as Admin):\n"
        '        setx GEMINI_API_KEY "<paste-your-key>"\n'
        "   - Restart this app\n"
    )

    print(
        "\n3️⃣  OLLAMA (FREE, NO SIGNUP, RUNS LOCALLY)\n"
        "   - Download: https://ollama.ai\n"
        "   - Install and run\n"
        "   - Pull a model: ollama pull llama2\n"
        "   - That's it! No API key needed.\n"
    )


def get_notebooklm_url() -> str:
    """Ask user for NotebookLM URL."""
    print(
        "\n" + "="*70
        "\nNOTEBOOKLM URL\n"
        "="*70
        "\nNotebookLM is optional (you can use just Gemini/Groq if you want).\n"
        "\nTo get your NotebookLM URL:\n"
        "  1. Open https://notebooklm.google.com\n"
        "  2. Create or open a notebook\n"
        "  3. Copy the URL from the address bar\n"
        "  4. Paste it here (or leave blank to skip)\n"
    )

    url = ask_input(
        "NotebookLM URL",
        default="https://notebooklm.google.com/notebook/...",
        required=False
    )

    if url and not url.startswith("https://notebooklm"):
        print("⚠️  That doesn't look like a NotebookLM URL. Using default.")
        return "https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID"

    return url if url and "..." not in url else ""


def create_config(api_results: dict, notebooklm_url: str) -> dict:
    """Build config.json from wizard answers."""
    providers = build_providers_from_validation(api_results)

    config = {
        "secret": "",  # Will be auto-generated
        "port": 5000,
        "default_mode": "notebook" if notebooklm_url else "gemini",
        "notebooks": {"default": notebooklm_url or ""},
        "providers": providers,
        "question_delimiter": "#",
        "memory_auto_route": True,
        "memory_auto_learn": True,
        "memory_max_entries": 12,
        "chat_memory_turns": 8,
        "short_answers": True,
        "history_enabled": True,
        "chrome_minimized": True,
        "startup_selftest": True,
    }

    return config


def save_config(config: dict):
    """Save config to file."""
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n✓ Config saved to {CONFIG_PATH}")


def main():
    clear_screen()
    print(
        "\n" + "="*70
        "\n🚀 NOTEBOOK-PHONE-SERVER SETUP WIZARD\n"
        "="*70
        "\nThis will guide you through setting up your AI phone server.\n"
        "Just answer a few questions and you're done!\n"
    )
    press_enter()

    # Step 1: Check environment
    clear_screen()
    print("\n" + "="*70)
    print("STEP 1: CHECKING SYSTEM")
    print("="*70)
    check_python()
    chrome_ok = check_chrome()

    # Step 2: Validate APIs
    clear_screen()
    api_results = validate_apis()

    # Step 3: Get NotebookLM URL (optional)
    clear_screen()
    notebooklm_url = get_notebooklm_url() if chrome_ok else ""

    # Step 4: Confirm and save
    clear_screen()
    print(
        "\n" + "="*70
        "\nSUMMARY\n"
        "="*70
    )
    working = [n for n, i in api_results.items() if i["valid"]]
    print(f"\n✓ AI Providers: {', '.join(working)}")
    print(f"✓ NotebookLM: {'Enabled' if notebooklm_url else 'Disabled'}")
    print(f"✓ Phone Password: Will be auto-generated and saved")

    if ask_yes_no("\nSave this configuration?", default=True):
        config = create_config(api_results, notebooklm_url)
        save_config(config)
        print(
            "\n" + "="*70
            "\n✓ SETUP COMPLETE!\n"
            "="*70
            "\nNext steps:\n"
            "  1. Close this window\n"
            "  2. Run: start.bat\n"
            "  3. Look for the phone server address in the console\n"
            "  4. Copy that address to your iPhone Shortcut\n"
            "\nEnjoy!"
        )
    else:
        print("\n❌ Setup cancelled.")
        sys.exit(1)

    press_enter()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
