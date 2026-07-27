from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.providers.factory import create_provider  # noqa: E402


async def main() -> None:
    settings = get_settings()
    provider = create_provider(settings)
    available, detail = await provider.health()
    locality = "may leave this machine" if provider.leaves_device else "is configured as local"
    print(
        f"Provider {settings.model_provider}/{settings.model_name}: {detail}; traffic {locality}."
    )
    raise SystemExit(0 if available else 1)


if __name__ == "__main__":
    asyncio.run(main())
