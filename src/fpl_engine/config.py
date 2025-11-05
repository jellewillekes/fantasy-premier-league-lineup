from __future__ import annotations
import os
from typing import Iterable

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def require(keys: Iterable[str]) -> None:
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


# Example usage:
# require(["FPL_API_BASE"])
# HORIZON = int(os.getenv("DEFAULT_HORIZON", "4"))
