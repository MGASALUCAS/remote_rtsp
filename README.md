# Mgasa RTSP Cloud Viewer

A Flask-based web application for viewing RTSP camera streams via MJPEG. Agents push JPEG frames to the server, and the web interface displays them as a live stream.

## Features

- Receive JPEG frames via POST requests to `/push/<camera_id>`
- View live MJPEG streams via `/stream/<camera_id>`
- Web interface for easy camera viewing
- Health check endpoint at `/health`

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access the web interface at `http://localhost:5000`

## DigitalOcean App Platform Deployment

This application is configured for easy deployment on DigitalOcean App Platform with autodeploy.

### Prerequisites

- A GitHub repository containing this code
- A DigitalOcean account

### Deployment Steps

1. **Push your code to GitHub** (if not already done):
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-github-repo-url>
git push -u origin main
```

2. **Update `.do/app.yaml`**:
   - Replace `your-username/your-repo-name` with your actual GitHub repository path
   - Adjust the `region` if needed (options: nyc, sfo, ams, sgp, lon, fra, tor, blr)

3. **Deploy via DigitalOcean Console**:
   - Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
   - Click "Create App"
   - Connect your GitHub repository
   - DigitalOcean will automatically detect the `.do/app.yaml` configuration
   - Review and deploy

4. **Or deploy via doctl CLI**:
```bash
doctl apps create --spec .do/app.yaml
```

### Configuration

The application uses the following environment variables:
- `PORT`: Server port (automatically set by DigitalOcean, defaults to 5000 locally)
- `FLASK_ENV`: Set to `production` to disable debug mode

### Endpoints

- `GET /` - Web interface for viewing camera streams
- `POST /push/<camera_id>` - Push JPEG frame data for a camera
- `GET /stream/<camera_id>` - MJPEG stream endpoint
- `GET /health` - Health check endpoint

### Usage

1. Default camera ID is `cam1`
2. Push frames to `/push/cam1` with JPEG bytes in the request body
3. View the stream at `/stream/cam1` or via the web interface

## Production Notes

- The application uses Gunicorn as the WSGI server in production
- Configured with 2 workers and 2 threads per worker
- Health checks are configured for automatic recovery
- Debug mode is disabled in production environments

