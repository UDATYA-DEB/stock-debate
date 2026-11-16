"""Create the default prompts in Langfuse if they don't exist yet (never overwrites).

Usage: python scripts/push_prompts.py   (keys from .env: LANGFUSE_PUBLIC_KEY etc.)
"""

import sys

from stockdebate.llm.config import DEFAULT_LANGFUSE_HOST, load_saved
from stockdebate.obs.tracing import Observability

saved = load_saved()
obs = Observability.from_keys(saved.get("langfuse_public_key"), saved.get("langfuse_secret_key"),
                              saved.get("langfuse_host", DEFAULT_LANGFUSE_HOST))
if not obs.enabled:
    sys.exit("Langfuse keys not found in .env (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY).")
pushed = obs.push_default_prompts()
obs.flush()
print(f"Pushed: {', '.join(pushed)}" if pushed else "All prompts already exist in Langfuse.")
