"""
WSGI entry point for the application.
This file is used by production servers like Gunicorn.
"""
from app import app

if __name__ == "__main__":
    app.run()

