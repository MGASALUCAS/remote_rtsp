# from flask import Flask, Response, request, render_template_string, jsonify
# import os
# import time

# app = Flask(__name__)

# # In-memory storage for latest frame per camera_id
# latest_frames = {}  # {camera_id: bytes}

# INDEX_HTML = """
# <!DOCTYPE html>
# <html>
# <head>
#   <meta charset="utf-8">
#   <title>Test Viewer</title>
#   <style>
#     body {
#       font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
#       background: #020617;
#       color: #e5e7eb;
#       display: flex;
#       flex-direction: column;
#       align-items: center;
#       min-height: 100vh;
#       padding: 1rem;
#     }
#     h1 { margin: 1rem 0; }
#     .info { font-size: 0.9rem; color: #9ca3af; text-align: center; }
#     img {
#       max-width: 100%;
#       height: auto;
#       border-radius: 0.75rem;
#       box-shadow: 0 10px 25px rgba(0,0,0,0.6);
#       background: #0f172a;
#       margin-top: 1rem;
#     }
#     input {
#       padding: 0.4rem 0.7rem;
#       border-radius: 0.5rem;
#       border: 1px solid #4b5563;
#       background: #020617;
#       color: #e5e7eb;
#     }
#     button {
#       margin-left: 0.5rem;
#       padding: 0.4rem 0.9rem;
#       border-radius: 999px;
#       border: none;
#       background: #22c55e;
#       color: #022c22;
#       font-weight: 600;
#       cursor: pointer;
#     }
#   </style>
# </head>
# <body>
#   <h1>Mgasa RTSP Cloud Test Viewer</h1>
#   <div class="info">
#     Default camera ID is <code>cam1</code>.<br>
#     Make sure your agent is pushing frames to <code>/push/cam1</code>.
#   </div>

#   <form onsubmit="event.preventDefault(); showStream();">
#     <input id="camId" type="text" value="cam1" />
#     <button type="submit">View Camera</button>
#   </form>

#   <img id="stream" src="" alt="Camera Stream will appear here">

#   <script>
#     function showStream() {
#       const id = document.getElementById('camId').value || 'cam1';
#       document.getElementById('stream').src = '/stream/' + id;
#     }
#     // auto-load default
#     showStream();
#   </script>
# </body>
# </html>
# """


# @app.route("/")
# def index():
#     return render_template_string(INDEX_HTML)


# @app.route("/push/<camera_id>", methods=["POST"])
# def push_frame(camera_id):
#     """
#     Agent sends raw JPEG bytes here.
#     """
#     latest_frames[camera_id] = request.data
#     return "ok", 200


# def generate_mjpeg(camera_id: str):
#     """
#     Yield MJPEG stream for the given camera_id.
#     """
#     while True:
#         frame = latest_frames.get(camera_id)
#         if frame is None:
#             # No frame yet, wait a bit
#             time.sleep(0.1)
#             continue

#         yield (
#             b"--frame\r\n"
#             b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
#         )
#         time.sleep(0.05)  # ~20 fps to viewer


# @app.route("/stream/<camera_id>")
# def stream(camera_id):
#     if camera_id not in latest_frames:
#         # We still return a stream; it will wait until frames arrive
#         pass

#     return Response(
#         generate_mjpeg(camera_id),
#         mimetype="multipart/x-mixed-replace; boundary=frame",
#     )


# @app.route("/health")
# def health():
#     return jsonify({"status": "ok"}), 200


# if __name__ == "__main__":
#     # Use PORT environment variable if available (for DigitalOcean), otherwise default to 5000
#     port = int(os.environ.get("PORT", 5000))
#     # Only enable debug mode if not in production
#     debug = os.environ.get("FLASK_ENV") != "production"
#     app.run(host="0.0.0.0", port=port, debug=debug)










"""
Mgasa RTSP Cloud Bridge
-----------------------

A small, production-friendly Flask app that:

- Receives JPEG frames from a LAN "agent" at POST /push/<camera_id>
- Streams live MJPEG to browsers at GET /stream/<camera_id>
- Shares frames across multiple workers using atomic file writes on disk
- Provides a minimal HTML viewer at /

This is designed to run behind gunicorn/nginx on port 80,
but also works directly with `python app.py` for testing.
"""

import os
import time
from typing import Dict, Any

from flask import Flask, Response, request, render_template_string, jsonify

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Base directory for this app (where app.py lives)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory where latest JPEG frame per camera will be stored
FRAME_DIR = os.path.join(BASE_DIR, "frames")
os.makedirs(FRAME_DIR, exist_ok=True)

# How often the streaming generator checks for new frames (seconds)
STREAM_POLL_INTERVAL = 0.03  # ~33 Hz

# How many seconds since last frame before we consider camera "stale"
STALE_SECONDS = 10.0


# ------------------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------------------

app = Flask(__name__)

# In-memory metadata (safe with multiple workers because it's not critical state)
# We only store timestamps here; actual frames are on disk shared by all workers.
camera_meta: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------------------

def frame_path(camera_id: str) -> str:
    """Return absolute path for the camera's latest JPEG frame."""
    safe_id = "".join(c for c in camera_id if c.isalnum() or c in ("-", "_"))
    return os.path.join(FRAME_DIR, f"{safe_id}.jpg")


def save_frame_atomic(camera_id: str, data: bytes) -> None:
    """
    Save JPEG data atomically for a camera.

    We write to a temporary file and then os.replace() it so that readers
    will never see a partially-written file, even under concurrency.
    """
    path_final = frame_path(camera_id)
    path_tmp = path_final + ".tmp"

    with open(path_tmp, "wb") as f:
        f.write(data)

    os.replace(path_tmp, path_final)


def get_camera_status(camera_id: str) -> Dict[str, Any]:
    """
    Return basic status info for a camera_id: last_seen, stale flag, etc.
    """
    meta = camera_meta.get(camera_id, {})
    last_seen = meta.get("last_seen", 0.0)
    now = time.time()
    age = now - last_seen if last_seen else None
    stale = age is None or age > STALE_SECONDS

    return {
        "camera_id": camera_id,
        "last_seen_ts": last_seen,
        "last_seen_age_sec": age,
        "is_stale": stale,
    }


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health() -> Response:
    """
    Health endpoint.

    Shows overall status plus a list of cameras we've seen frames for.
    """
    # Collect camera statuses based on files present in FRAME_DIR
    cameras = []
    for fname in os.listdir(FRAME_DIR):
        if not fname.endswith(".jpg"):
            continue
        cam_id = fname[:-4]  # strip .jpg
        cameras.append(get_camera_status(cam_id))

    return jsonify(
        {
            "status": "ok",
            "camera_count": len(cameras),
            "cameras": cameras,
        }
    )


@app.route("/push/<camera_id>", methods=["POST"])
def push_frame(camera_id: str) -> Response:
    """
    LAN agent sends raw JPEG bytes here via HTTP POST.

    Example from the agent:
      POST http://your-server/push/cam1
      body: <JPEG bytes>
    """
    data = request.data
    if not data:
        return "no data", 400

    try:
        save_frame_atomic(camera_id, data)
    except Exception as e:
        # Log the error; in production you might integrate with proper logging
        print(f"[server] Error writing frame for {camera_id}: {e}")
        return "error", 500

    # Update metadata (non-critical, per-process is fine)
    camera_meta.setdefault(camera_id, {})
    camera_meta[camera_id]["last_seen"] = time.time()

    return "ok", 200


def generate_mjpeg(camera_id: str):
    """
    Generator that yields an MJPEG stream for the given camera_id.

    It watches the JPEG file for that camera and sends a new frame whenever
    the file's mtime changes, yielding multipart HTTP chunks.
    """
    path = frame_path(camera_id)
    last_mtime = 0.0

    while True:
        try:
            mtime = os.path.getmtime(path)
            if mtime != last_mtime:
                last_mtime = mtime
                with open(path, "rb") as f:
                    frame = f.read()

                # Yield one MJPEG frame
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
        except FileNotFoundError:
            # No frame yet; agent may not have pushed anything
            pass
        except Exception as e:
            print(f"[server] Error reading frame for {camera_id}: {e}")

        time.sleep(STREAM_POLL_INTERVAL)


@app.route("/stream/<camera_id>", methods=["GET"])
def stream(camera_id: str) -> Response:
    """
    Browser hits this URL to see live video for the given camera_id.

    Example:
      <img src="/stream/cam1">

    This returns an infinite multipart/x-mixed-replace response streaming MJPEG.
    """
    resp = Response(
        generate_mjpeg(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
    # Disable caching
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ------------------------------------------------------------------------------
# Minimal viewer UI
# ------------------------------------------------------------------------------

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mgasa RTSP Cloud Viewer</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #020617;
      color: #e5e7eb;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      margin: 0;
      padding: 1.5rem 1rem;
    }
    h1 { margin: 0.5rem 0 0.75rem 0; }
    .info {
      font-size: 0.9rem;
      color: #9ca3af;
      text-align: center;
      max-width: 600px;
      margin-bottom: 1rem;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    input {
      padding: 0.35rem 0.7rem;
      border-radius: 0.5rem;
      border: 1px solid #4b5563;
      background: #020617;
      color: #e5e7eb;
      min-width: 120px;
    }
    button {
      padding: 0.4rem 0.9rem;
      border-radius: 999px;
      border: none;
      background: #22c55e;
      color: #022c22;
      font-weight: 600;
      cursor: pointer;
    }
    button:hover {
      background: #16a34a;
    }
    img {
      max-width: 100%;
      height: auto;
      border-radius: 0.75rem;
      box-shadow: 0 10px 25px rgba(0,0,0,0.6);
      background: #0f172a;
    }
  </style>
</head>
<body>
  <h1>Mgasa RTSP Cloud Viewer</h1>
  <div class="info">
    This page streams live MJPEG from your LAN camera via the cloud bridge.<br>
    Default camera ID is <code>cam1</code>. Make sure your LAN agent posts frames to <code>/push/cam1</code>.
  </div>

  <div class="controls">
    <label for="camId">Camera ID:</label>
    <input id="camId" type="text" value="cam1" />
    <button type="button" onclick="loadStream()">View</button>
  </div>

  <img id="streamImg" src="" alt="Live stream will appear here">

  <script>
    function loadStream() {
      const camId = document.getElementById('camId').value || 'cam1';
      const img = document.getElementById('streamImg');
      // Add a cache buster in case browser tries to reuse old connection
      img.src = '/stream/' + encodeURIComponent(camId) + '?t=' + Date.now();
    }
    // Auto-load default on page load
    window.addEventListener('DOMContentLoaded', loadStream);
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index() -> Response:
    return render_template_string(INDEX_HTML)


# ------------------------------------------------------------------------------
# Entry point (for local testing)
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # For local/dev usage:
    #   python app.py
    # Then open http://localhost:8000/
    #
    # In production on DO you'd typically run something like:
    #   gunicorn -w 3 -b 0.0.0.0:8000 app:app
    # behind nginx reverse proxy on port 80.
    app.run(host="0.0.0.0", port=8000, debug=True, threaded=True)
