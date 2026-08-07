"""Run the site: `python -m stockanalyser.web`  (honours $PORT / $HOST)."""
from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    uvicorn.run(
        "stockanalyser.web.app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("RELOAD")),
    )


if __name__ == "__main__":
    main()
