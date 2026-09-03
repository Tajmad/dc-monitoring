import os
import sys
from streamlit.web.cli import main

if __name__ == "__main__":
    if hasattr(sys, '_MEIPASS'):
        app_path = os.path.join(sys._MEIPASS, "app.py")
    else:
        app_path = "app.py"

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port=8501",
        "--server.headless=true",
        "--global.developmentMode=false"
    ]
    main()