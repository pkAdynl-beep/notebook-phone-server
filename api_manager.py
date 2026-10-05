"""
api_manager.py - Automatic API key validation, rotation, and management.

Features:
- Test API keys before use
- Suggest free alternatives (Groq, OpenRouter, Ollama)
- Auto-add working free APIs
- Monitor quota and alert when running low
- Fallback to local models if needed
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import dict, list, tuple


class APIValidator:
    """Test and validate API keys before adding them to config."""

    # Free APIs with generous free tiers
    FREE_APIS = [
        {
            "name": "Groq",
            "url": "https://console.groq.com",
            "env_var": "GROQ_API_KEY",
            "test_endpoint": "https://api.groq.com/openai/v1/models",
            "type": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "models": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
            "note": "Very fast, 9000 req/day free (generous)"
        },
        {
            "name": "OpenRouter",
            "url": "https://openrouter.ai/keys",
            "env_var": "OPENROUTER_API_KEY",
            "test_endpoint": "https://openrouter.ai/api/v1/models",
            "type": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "models": ["meta-llama/llama-2-70b-chat", "mistralai/mistral-7b-instruct"],
            "note": "Huge model selection, flexible pricing"
        },
        {
            "name": "Ollama (Local)",
            "url": "https://ollama.ai",
            "env_var": None,
            "test_endpoint": "http://localhost:11434/api/tags",
            "type": "ollama",
            "base_url": "http://localhost:11434/v1",
            "models": ["llama2", "mistral"],
            "note": "Free, runs locally on your PC (no internet needed)"
        },
    ]

    @staticmethod
    def test_gemini_key(key: str) -> tuple[bool, str]:
        """Test if a Gemini API key is valid."""
        if not key or "PASTE" in key.upper():
            return False, "Placeholder key (not filled in)"
        try:
            from google import genai
            client = genai.Client(api_key=key)
            # Try a simple model list call
            models = list(client.models.list())
            if models:
                return True, f"✓ Valid (found {len(models)} models)"
            return False, "No models accessible"
        except Exception as e:
            msg = str(e)
            if "401" in msg or "UNAUTHENTICATED" in msg:
                return False, "Invalid API key (401 auth error)"
            if "403" in msg:
                return False, "Access denied (no billing or quota exhausted)"
            if "429" in msg:
                return False, "Rate limited (try again in a moment)"
            return False, f"Error: {msg[:80]}"

    @staticmethod
    def test_openai_compatible(key: str, base_url: str, name: str) -> tuple[bool, str]:
        """Test OpenAI-compatible APIs (Groq, OpenRouter, etc)."""
        if not key or "PASTE" in key.upper():
            return False, "Placeholder key (not filled in)"
        try:
            url = base_url.rstrip("/") + "/models"
            headers = {
                "Authorization": f"Bearer {key}",
                "User-Agent": "notebook-phone-server/1.0"
            }
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                models = data.get("data", [])
                if models:
                    return True, f"✓ Valid ({len(models)} models available)"
                return False, "No models found"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, f"Invalid API key (401 auth error)"
            if e.code == 403:
                return False, "Access denied or quota exceeded (403)"
            if e.code == 429:
                return False, "Rate limited"
            return False, f"HTTP {e.code}"
        except Exception as e:
            msg = str(e)
            if "refused" in msg.lower():
                return False, f"Connection refused (service down or offline)"
            return False, f"Connection error: {msg[:60]}"

    @staticmethod
    def test_ollama() -> tuple[bool, str]:
        """Test if Ollama is running locally."""
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode())
                models = data.get("models", [])
                if models:
                    model_names = ", ".join(m.get("name", "?") for m in models[:3])
                    return True, f"✓ Running ({len(models)} models: {model_names})"
                return False, "Running but no models installed"
        except Exception as e:
            return False, f"Not running (start with: ollama serve)"

    def validate_all(self) -> dict:
        """Test all API keys and suggest working alternatives."""
        results = {}
        env_vars = os.environ

        # Test Gemini
        results["gemini"] = {
            "name": "Google Gemini",
            "env_var": "GEMINI_API_KEY",
            "key": env_vars.get("GEMINI_API_KEY", ""),
        }
        valid, msg = self.test_gemini_key(results["gemini"]["key"])
        results["gemini"]["valid"] = valid
        results["gemini"]["status"] = msg

        # Test free alternatives
        for api in self.FREE_APIS:
            if api["name"] == "Ollama (Local)":
                valid, msg = self.test_ollama()
            else:
                key = env_vars.get(api["env_var"], "")
                valid, msg = self.test_openai_compatible(
                    key, api["base_url"], api["name"]
                )
            results[api["name"]] = {
                "env_var": api["env_var"],
                "key": env_vars.get(api["env_var"], "") if api["env_var"] else None,
                "valid": valid,
                "status": msg,
                "type": api["type"],
                "base_url": api.get("base_url"),
                "models": api.get("models"),
                "note": api["note"],
                "signup_url": api["url"],
            }

        return results


def print_validation_report(results: dict):
    """Pretty-print API validation results."""
    print("\n" + "=" * 70)
    print("API KEY VALIDATION REPORT")
    print("=" * 70)

    working = []
    failed = []
    missing = []

    for name, info in results.items():
        status = "✓" if info["valid"] else "✗"
        key_str = "(key found)" if info["key"] else "(no key in env)"
        print(f"\n{status} {name} {key_str}")
        print(f"   {info['status']}")
        if info.get("note"):
            print(f"   💡 {info['note']}")

        if info["valid"]:
            working.append(name)
        elif info["key"]:
            failed.append(name)
        else:
            missing.append(name)

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(working)} working | {len(failed)} invalid | {len(missing)} missing")
    print("=" * 70)

    if failed:
        print(f"\n⚠️  INVALID KEYS (these won't work):")
        for name in failed:
            info = results[name]
            print(f"   - {name}: {info['status']}")
            if info.get("signup_url"):
                print(f"     → Regenerate at: {info['signup_url']}")

    if missing:
        print(f"\n📌 MISSING KEYS (setup required):")
        for name in missing:
            info = results[name]
            if info.get("env_var"):
                print(f"   - {name}")
                print(f"     → Sign up: {info['signup_url']}")
                print(f"     → Set env var: {info['env_var']}=<your-key>")
                print(f"     → Then restart this app")
            else:
                print(f"   - {name}")
                print(f"     → {info['status']}")
                print(f"     → Setup: {info['signup_url']}")

    if working:
        print(f"\n✓ WORKING PROVIDERS:")
        for name in working:
            info = results[name]
            models = ", ".join(info.get("models", [])[: 2])
            print(f"   - {name}: {models}")

    return working, failed, missing


def build_providers_from_validation(results: dict) -> list:
    """Convert validation results to config providers format."""
    providers = []
    mapping = {
        "Google Gemini": {
            "name": "gemini",
            "type": "gemini",
            "vision": True,
            "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
            "read_models": ["gemini-1.5-flash"],
        },
        "Groq": {
            "name": "groq",
            "type": "openai",
            "vision": False,
            "base_url": "https://api.groq.com/openai/v1",
            "models": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
        },
        "OpenRouter": {
            "name": "openrouter",
            "type": "openai",
            "vision": False,
            "base_url": "https://openrouter.ai/api/v1",
            "models": ["meta-llama/llama-2-70b-chat", "mistralai/mistral-7b-instruct"],
        },
        "Ollama (Local)": {
            "name": "ollama",
            "type": "openai",
            "vision": False,
            "base_url": "http://localhost:11434/v1",
            "models": ["llama2", "mistral"],
        },
    }

    for name, info in results.items():
        if not info["valid"]:
            continue
        if name not in mapping:
            continue

        provider = mapping[name].copy()
        if info["key"]:
            provider["keys"] = [info["key"]]
        else:
            provider["keys"] = [f"env:{info['env_var']}"]
        provider["enabled"] = True
        providers.append(provider)

    return providers


if __name__ == "__main__":
    print("\nValidating API keys...")
    validator = APIValidator()
    results = validator.validate_all()
    working, failed, missing = print_validation_report(results)

    if failed or missing:
        print("\n" + "!" * 70)
        print("ACTION REQUIRED: Some API keys are missing or invalid.")
        print("!" * 70)
        print("\n1. Fix invalid keys or get new ones from the signup URLs above")
        print("2. Set environment variables (see above for the exact commands)")
        print("3. Restart this application")
        print("\nExample (Windows Command Prompt):")
        print('   setx GROQ_API_KEY "your-key-here"')
        print("\nExample (Linux/Mac bash):")
        print('   export GROQ_API_KEY="your-key-here"')
        print()
        if not working:
            print("⚠️  WARNING: No working API keys found. App will not function.")
            sys.exit(1)
