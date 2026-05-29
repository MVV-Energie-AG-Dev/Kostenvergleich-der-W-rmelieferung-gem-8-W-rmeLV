"""
Launcher für die Streamlit-App als EXE (PyInstaller).
Startet Streamlit direkt im Prozess und öffnet den Browser automatisch.
"""
import multiprocessing
import os
import sys
import threading
import webbrowser
import time


def open_browser():
    time.sleep(5)
    webbrowser.open("http://localhost:8501")


def run_streamlit(app_path):
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.headless=true",
        "--server.port=8501",
        "--browser.serverAddress=localhost",
        "--server.fileWatcherType=none",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    # WICHTIG: verhindert, dass Streamlit-Subprozesse den Launcher neu starten
    multiprocessing.freeze_support()

    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    app_path = os.path.join(base_path, "app.py")

    threading.Thread(target=open_browser, daemon=True).start()
    run_streamlit(app_path)
