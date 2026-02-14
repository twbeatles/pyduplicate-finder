import os
import sys

# Ensure the repo root is importable so `import src.*` works in all tests.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

