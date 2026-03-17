"""Startup shim — changes to nutracomply/ and starts the FastAPI server."""
import os, sys, subprocess

os.chdir(os.path.join(os.path.dirname(__file__), "nutracomply"))
sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app",
                          "--host", "0.0.0.0", "--port", "8000", "--reload"]))
