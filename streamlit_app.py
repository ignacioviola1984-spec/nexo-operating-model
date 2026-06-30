"""Streamlit Community Cloud entry point -> the Nexo v3 CV/portfolio demo.

Placed at the repo root so the `nexo_os` package is importable on Streamlit
Cloud (which adds the entry script's directory to sys.path) without an editable
install. Locally you can still run either:
    streamlit run streamlit_app.py            # the demo
    streamlit run nexo_os/dashboard/demo.py   # same demo
    streamlit run nexo_os/dashboard/app.py    # the production app (login)

The demo uses 100% synthetic data and makes no outbound calls (offline prose),
so it is safe to host publicly. No secrets required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nexo_os.dashboard.demo  # noqa: E402,F401  (module runs the demo on import)
