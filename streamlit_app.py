"""Entry point for Streamlit Cloud. Living at the repo root means every module is inside the
folder Streamlit watches, so pushes reload config.py and src/ without a manual reboot."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parent / "src" / "dashboard" / "app.py"), run_name="__main__")
