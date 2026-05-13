import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.app import App

if __name__ == "__main__":
    App().run()
