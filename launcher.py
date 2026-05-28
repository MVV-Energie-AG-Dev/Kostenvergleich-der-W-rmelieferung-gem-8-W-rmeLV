"""
Launcher für die Streamlit-App als EXE (PyInstaller).
Startet den lokalen Streamlit-Server und öffnet den Browser automatisch.
"""
import os
import sys
import subprocess
import threading
import webbrowser
import time


def open_browser():
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    # Pfad zu app.py ermitteln (funktioniert sowohl als .py als auch als .exe)
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    app_path = os.path.join(base_path, "app.py")

    threading.Thread(target=open_browser, daemon=True).start()

    subprocess.run(
        [
            sys.executable,
            "-m", "streamlit", "run", app_path,
            "--server.headless", "true",
            "--server.port", "8501",
            "--browser.serverAddress", "localhost",
            "--server.fileWatcherType", "none",
        ]
    )
