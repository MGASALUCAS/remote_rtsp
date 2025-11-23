from flask import Flask, Response, request, render_template_string
import os
import time

app = Flask(__name__)

# In-memory storage for latest frame per camera_id
latest_frames = {}  # {camera_id: bytes}


INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mgasa Cloud Viewer</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #020617;
      color: #e5e7eb;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    h1 { margin: 1rem 0; }
    .info { font-size: 0.9rem; color: #9ca3af; text-align: center; }
    img {
      max-width: 100%;
      height: auto;
      border-radius: 0.75rem;
      box-shadow: 0 10px 25px rgba(0,0,0,0.6);
      background: #0f172a;
      margin-top: 1rem;
    }
    input {
      padding: 0.4rem 0.7rem;
      border-radius: 0.5rem;
      border: 1px solid #4b5563;
      background: #020617;
      color: #e5e7eb;
    }
    button {
      margin-left: 0.5rem;
      padding: 0.4rem 0.9rem;
      border-radius: 999px;
      border: none;
      background: #22c55e;
      color: #022c22;
      font-weight: 600;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <h1>Mgasa RTSP Cloud Viewer</h1>
  <div class="info">
    Default camera ID is <code>cam1</code>.<br>
    Make sure your agent is pushing frames to <code>/push/cam1</code>.
  </div>

  <form onsubmit="event.preventDefault(); showStream();">
    <input id="camId" type="text" value="cam1" />
    <button type="submit">View Camera</button>
  </form>

  <img id="stream" src="" alt="Camera Stream will appear here">

  <script>
    function showStream() {
      const id = document.getElementById('camId').value || 'cam1';
      document.getElementById('stream').src = '/stream/' + id;
    }
    // auto-load default
    showStream();
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/push/<camera_id>", methods=["POST"])
def push_frame(camera_id):
    """
    Agent sends raw JPEG bytes here.
    """
    latest_frames[camera_id] = request.data
    return "ok", 200


def generate_mjpeg(camera_id: str):
    """
    Yield MJPEG stream for the given camera_id.
    """
    while True:
        frame = latest_frames.get(camera_id)
        if frame is None:
            # No frame yet, wait a bit
            time.sleep(0.1)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.05)  # ~20 fps to viewer


@app.route("/stream/<camera_id>")
def stream(camera_id):
    if camera_id not in latest_frames:
        # We still return a stream; it will wait until frames arrive
        pass

    return Response(
        generate_mjpeg(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # Use PORT environment variable if available (for DigitalOcean), otherwise default to 5000
    port = int(os.environ.get("PORT", 5000))
    # Only enable debug mode if not in production
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
