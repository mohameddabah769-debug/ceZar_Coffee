import os
import sys

# ضمان مسار المشروع الرئيسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.chdir(BASE_DIR)

from app.flask_app import app as application
app = application

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
