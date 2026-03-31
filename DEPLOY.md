# Deploy Guide — TrafficIQ to GitHub + Render.com

## Step 1 — Install Git (if not already)

Open a new terminal and check:
```
git --version
```
If not installed → https://git-scm.com/download/win  
Install with default options, then **restart your terminal**.

---

## Step 2 — Configure Git identity (one-time setup)

```
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

---

## Step 3 — Create GitHub repository

1. Go to https://github.com/new
2. Set **Repository name**: `trafficiq`
3. Set **Visibility**: Public *(Render free tier requires public repo)*
4. **Do NOT** tick "Add README" or "Add .gitignore"
5. Click **Create repository**
6. Copy the URL shown — it will look like:  
   `https://github.com/YOUR_USERNAME/trafficiq.git`

---

## Step 4 — Push your code

Run these commands in `D:\traffic_monitor` (with your venv active):

```cmd
cd D:\traffic_monitor

git init
git branch -M main

git add .
git commit -m "Initial commit: TrafficIQ monitoring system"

git remote add origin https://github.com/YOUR_USERNAME/trafficiq.git
git push -u origin main
```

When prompted, sign in with your GitHub credentials.  
*(If asked for a password, use a GitHub Personal Access Token — Settings → Developer Settings → Personal access tokens → Generate new token → tick `repo`)*

---

## Step 5 — Deploy on Render.com

1. Go to https://render.com and **sign up / log in** (use "Continue with GitHub")

2. Click **New +** → **Web Service**

3. Connect your GitHub account if not already, then select the `trafficiq` repo

4. Fill in the settings:

   | Field | Value |
   |---|---|
   | **Name** | `trafficiq` |
   | **Region** | Oregon (US West) |
   | **Branch** | `main` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `chmod +x build.sh && ./build.sh` |
   | **Start Command** | `gunicorn app:app --workers=1 --threads=8 --bind=0.0.0.0:$PORT --timeout=120` |
   | **Instance Type** | Free |

5. Click **Advanced** → **Add Disk**:
   - Name: `trafficiq-data`
   - Mount Path: `/opt/render/project/src/instance`
   - Size: 1 GB

6. Click **Create Web Service**

Render will now build and deploy. Build takes ~5–8 minutes (torch download is ~800 MB).  
Your live URL will be: `https://trafficiq.onrender.com`

---

## Step 6 — Future deployments (automatic)

Every `git push` to `main` triggers a new Render deploy automatically.

```cmd
git add .
git commit -m "your message"
git push
```

---

## ⚠ Free Tier Limitations

| Limitation | Impact |
|---|---|
| **Spins down after 15 min inactivity** | First visit after idle takes ~30s to wake up |
| **~0.5 vCPU** | YOLO inference on 3 streams will be slow (~1–2 FPS) |
| **512 MB RAM** | EasyOCR + YOLO together use ~400 MB — tight but OK |
| **750 free hours/month** | Enough for ~1 instance running continuously |
| **No persistent disk on free plan** | Alert history resets on each deploy unless you add the disk ($0.25/GB/mo) |

**For a smoother demo**: disable cameras 1 and 2 in `app.py` `CAMERAS` list and only run one feed.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Build failed: ./build.sh: Permission denied` | Render may need `bash build.sh` as build command instead |
| `ModuleNotFoundError: torch` | Build command didn't run — check Render logs under "Build" tab |
| `Video file not found` | mp4 files must be committed to git (check `.gitignore` doesn't exclude them) |
| `Port already in use` | Render sets `$PORT` automatically — don't hardcode 5000 |
| App sleeps / slow first load | Normal on free tier — upgrade to Starter ($7/mo) to prevent sleep |