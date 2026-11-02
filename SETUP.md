# Cloud File Uploader — Setup Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | https://python.org |
| pip | latest | bundled with Python |
| Node.js | 18+ | https://nodejs.org |
| npm | 9+ | bundled with Node |
| Docker Desktop | latest | https://docker.com (for local emulator) |
| Google Cloud SDK | latest | https://cloud.google.com/sdk (for production only) |

---

## Step-by-Step Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/cloud-file-uploader.git
cd cloud-file-uploader
```

---

## Option A: Local Emulator Setup (No GCP Billing)

> Recommended for development and interview demos. Uses `fsouza/fake-gcs-server` in Docker.

### A1. Start Docker Desktop

Open Docker Desktop and wait until the engine is running.

### A2. Start the GCS emulator container

```bash
# Check if container already exists
docker ps -a --filter "name=cloudvault-gcs"

# First time — create and start:
docker run -d --name cloudvault-gcs ^
  -p 4443:4443 ^
  -v "C:/absolute/path/to/project/backend/cloudstorage:/data" ^
  fsouza/fake-gcs-server ^
  -scheme http -port 4443 -public-host localhost:4443

# If the container already exists but is stopped:
docker start cloudvault-gcs

# Verify emulator is responding:
curl http://localhost:4443/storage/v1/b
```

> **Windows note:** Use absolute paths with forward slashes in the `-v` flag.

### A3. Create the emulator bucket

```bash
cd backend
venv\Scripts\python -c "from google.cloud import storage; from google.auth.credentials import AnonymousCredentials; c=storage.Client(project='cloudvault-local',credentials=AnonymousCredentials(),client_options={'api_endpoint':'http://localhost:4443'}); b=c.bucket('cloudvault-demo'); b.create() if not b.exists() else print('already exists'); print('bucket status:', b.exists())"
```

### A4. Configure backend for emulator

```bash
cd backend
cp .env.example .env
```

`backend/.env` should contain:
```
GCS_BUCKET_NAME=cloudvault-demo
GOOGLE_CLOUD_PROJECT=cloudvault-local
STORAGE_EMULATOR_HOST=http://localhost:4443
STORAGE_EMULATOR_MODE=true
PORT=5000
FLASK_DEBUG=1
ALLOWED_ORIGINS=http://localhost:3000
```

### A5. Install and run backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
python app.py
```

### A6. Configure and run frontend

```bash
cd frontend
cp .env.example .env
# frontend/.env should contain: VITE_BACKEND_URL=http://localhost:5000
npm install
npm run dev
```

### A7. Verify

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:5000 |
| Health | http://localhost:5000/health |
| Emulator | http://localhost:4443 |

---

## Option B: Production Google Cloud Storage

### 2. Google Cloud Storage

```bash
# Authenticate (one-time)
gcloud auth login
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Create a private bucket
gsutil mb -p YOUR_PROJECT_ID -l us-central1 gs://YOUR_BUCKET_NAME

# Create a service account for the backend
gcloud iam service-accounts create file-uploader-sa \
  --display-name="File Uploader Service Account"

# Grant Storage Admin role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:file-uploader-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# Grant Token Creator (needed for v4 signed URLs)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:file-uploader-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# Download service account key (local dev only)
gcloud iam service-accounts keys create backend/service-account-key.json \
  --iam-account=file-uploader-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 3. Backend configuration

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:
```
GCS_BUCKET_NAME=your-bucket-name
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=C:/absolute/path/to/backend/service-account-key.json
FLASK_DEBUG=1
PORT=5000
```

### 4. Install backend dependencies

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Frontend configuration

```bash
cd ../frontend
cp .env.example .env
```

`frontend/.env` should contain:
```
VITE_BACKEND_URL=http://localhost:5000
```

### 6. Install frontend dependencies

```bash
npm install
```

---

## Running the Application

Open **two terminals**:

```bash
# Terminal 1 — Backend (from project root)
cd backend
venv\Scripts\python app.py          # Windows
# OR: source venv/bin/activate && python app.py  (Linux/macOS)

# Terminal 2 — Frontend (from project root)
cd frontend
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:5000 |
| Health Check | http://localhost:5000/health |

---

## Testing

```bash
# 1. Health check
curl http://localhost:5000/health

# 2. Upload a file
curl -X POST http://localhost:5000/upload \
  -F "file=@/path/to/test.txt"

# 3. List files
curl http://localhost:5000/files

# 4. Delete a file (use the 'name' from /files response)
curl -X DELETE "http://localhost:5000/delete/abc123_test.txt"
```

---

## Cloud Run Deployment

```bash
cd backend

# Build and push
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/cloud-file-uploader

# Deploy
gcloud run deploy cloud-file-uploader \
  --image gcr.io/YOUR_PROJECT_ID/cloud-file-uploader \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account=file-uploader-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GCS_BUCKET_NAME=YOUR_BUCKET_NAME \
  --set-env-vars CORS_ORIGIN=https://your-frontend.vercel.app
```

After deploying, update `frontend/.env` (or Vercel env vars):
```
VITE_BACKEND_URL=https://YOUR_CLOUD_RUN_URL
```

---

## Pushing to Your Own GitHub Repository

```bash
# Remove the original remote
git remote remove origin

# Add your friend's repository as origin
git remote add origin https://github.com/YOUR_FRIEND/cloud-file-uploader.git

# Verify .gitignore is correct (check that .env and *.json keys are excluded)
git status

# Stage and commit all changes
git add .
git commit -m "feat: full CRUD endpoints, env-var config, signed URLs, list/delete UI"

# Push
git push -u origin main
```

> ⚠️ Before pushing, confirm `git status` does NOT show `.env` files or `service-account-key.json`.

---

## Emulator Management

```bash
# Start emulator (if stopped)
docker start cloudvault-gcs

# Stop emulator (data persists in volume)
docker stop cloudvault-gcs

# View emulator logs
docker logs cloudvault-gcs

# Remove container (data remains in backend/cloudstorage/)
docker rm cloudvault-gcs

# View stored files directly
dir backend\cloudstorage\cloudvault-demo\
```

> **Note:** Emulator data is stored in `backend/cloudstorage/` via Docker volume.
> This folder is in `.gitignore` and will NOT be committed.

---

## Switching Between Emulator and Production

Edit `backend/.env`:
- **Emulator mode:** `STORAGE_EMULATOR_MODE=true` + `STORAGE_EMULATOR_HOST=http://localhost:4443`
- **Production mode:** `STORAGE_EMULATOR_MODE=false` + `STORAGE_EMULATOR_HOST=` (empty)

Restart the backend after changing modes.

---

## What Has Been Modified

| File | Change |
|------|--------|
| `backend/app.py` | Full rewrite: added `/health`, `/files`, `/delete/<filename>` endpoints; env-var config; CORS fix; file validation; signed URLs; secure filenames |
| `backend/requirements.txt` | Added Werkzeug pin for Flask 2.3 compatibility |
| `backend/.env.example` | Removed hardcoded original bucket name; documented all variables |
| `backend/.env` | Created for local dev (not committed) |
| `backend/Dockerfile` | Fixed: copies only `app.py` (not credentials); documented Cloud Run SA approach |
| `backend/.gitignore` | Fixed: replaced `*.json` wildcard with specific key patterns |
| `frontend/src/components/FileUpload.jsx` | Added file list, per-file download, per-file delete, health badge, file size/date display |
| `frontend/.env.example` | Points to `localhost:5000` instead of original Cloud Run URL |
| `frontend/.env` | Created for local dev (not committed) |
| `.gitignore` | Fixed: removed dangerous `*.json` wildcard; added venv, specific key patterns |
| `README.md` | Full rewrite with attribution, architecture, all endpoints, security |
| `SETUP.md` | Full rewrite with step-by-step GCP setup, testing, Cloud Run deploy |
