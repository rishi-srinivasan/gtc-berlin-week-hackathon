"""Apply the active profile of config.toml as environment defaults (real env / .env always win).

  uv run python -m pii.config            # show effective settings + check local Ollama models
  PII_PROFILE=hackathon make eval ...    # switch profile for one command
"""
import os
import tomllib
from pathlib import Path


def find_config() -> Path | None:
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "config.toml").exists():
            return d / "config.toml"
    return None


def profile_values() -> tuple[str, dict]:
    path = find_config()
    if not path:
        return "none", {}
    cfg = tomllib.loads(path.read_text())
    name = os.getenv("PII_PROFILE") or cfg.get("profile", "local")
    if name not in cfg.get("profiles", {}):
        raise SystemExit(f"PII_PROFILE={name!r} not in {path} (have: {', '.join(cfg.get('profiles', {}))})")
    return name, cfg["profiles"][name]


def apply() -> str:
    name, values = profile_values()
    for k, v in values.items():
        if v and not str(v).startswith("<"):  # "" and "<placeholder>" stay unset
            os.environ.setdefault(k, str(v))
    return name


def main():
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))
    name, values = profile_values()
    print(f"profile: {name}")
    for k, v in values.items():
        cur = os.getenv(k)
        note = "" if cur == str(v) else f"   <- overridden by env: {cur!r}" if cur else "   <- UNSET (placeholder)"
        print(f"  {k} = {v!r}{note}")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "RUNPOD_API_KEY"):
        print(f"  {key}: {'set' if os.getenv(key) else 'missing'}")
    if "ollama" in {os.getenv("TEACHER_PROVIDER"), os.getenv("STUDENT_PROVIDER"), os.getenv("FRONTIER_PROVIDER")}:
        import httpx
        try:
            have = {m["name"] for m in httpx.get(os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/tags").json()["models"]}
            for role in ("TEACHER", "STUDENT", "FRONTIER"):
                if os.getenv(f"{role}_PROVIDER") == "ollama":
                    m = os.getenv(f"{role}_MODEL")
                    print(f"  ollama {role.lower()} {m}: {'ok' if m in have else 'NOT PULLED -> ollama pull ' + str(m)}")
        except httpx.HTTPError:
            print("  ollama: not reachable (start it with `ollama serve`)")


if __name__ == "__main__":
    main()
