"""Runtime integration shared by packaged plugins (Python 3.11+)."""
import os
from pathlib import Path


def runtime_name(env=None):
    env = os.environ if env is None else env
    selected = env.get("AGENT_RUNTIME")
    if selected is None:
        selected = "codex" if env.get("PLUGIN_ROOT") else "claude"
    if selected not in {"claude", "codex"}:
        raise ValueError("AGENT_RUNTIME must be claude or codex")
    return selected


def agent_home(env=None):
    env = os.environ if env is None else env
    runtime = runtime_name(env)
    key = "CODEX_HOME" if runtime == "codex" else "CLAUDE_CONFIG_DIR"
    return Path(env.get(key) or str(Path.home() / ("." + runtime))).expanduser()


def data_dir(plugin, env=None):
    env = os.environ if env is None else env
    if runtime_name(env) == "codex" and env.get("PLUGIN_DATA"):
        return Path(env["PLUGIN_DATA"]).expanduser()
    return agent_home(env) / plugin
