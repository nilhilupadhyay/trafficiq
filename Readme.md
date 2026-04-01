# TrafficIQ — Intelligent Traffic Monitoring System

> **Real-time multi-camera vehicle tracking, stopped-vehicle detection, and ANPR powered by YOLOv8 + Flask.**

---

## Table of Contents
1. [Features](#features)
2. [System Architecture](#system-architecture)
3. [Project Structure](#project-structure)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Deployment](#deployment)
7. [Roadmap / Enhancement Ideas](#roadmap--enhancement-ideas)
8. [Troubleshooting](#troubleshooting)

---

## Features

| Feature | Description |
|---|---|
| 🎥 **Multi-camera MJPEG streaming** | Live YOLOv8-annotated feeds for up to N cameras |
| 🚗 **Vehicle detection & tracking** | Cars, motorcycles, buses, trucks via YOLOv8n |
| 🛑 **Stopped-vehicle alerts** | Size-normalised sliding-window algorithm (no fixed pixel threshold) |
| 🔤 **ANPR** | EasyOCR smart-crop plate extraction on first alert |
| 🔔 **Browser TTS notifications** | Web Speech API announces alerts audibly |
| 📊 **Live stats dashboard** | Per-camera vehicle count, stopped count, total alerts |
| 📜 **Persistent alert log** | SQLite via SQLAlchemy; paginated history page |
| 🔍 **Client-side alert filtering** | Instant search on the history page |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (Client)                      │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │  MJPEG feed │  │  Stats poller │  │  Alerts poller   │  │
│  │  <img src>  │  │  /api/stats   │  │  /api/alerts     │  │
│  └──────┬──────┘  └──────┬────────┘  └────────┬─────────┘  │
└─────────┼────────────────┼────────────────────┼────────────┘
          │ HTTP           │ JSON               │ JSON
┌─────────▼────────────────▼────────────────────▼────────────┐
│                    Flask App  (app.py)                       │
│                                                              │
│  /video_feed/<id>          /api/stats        /api/alerts    │
│       │                        │                  │         │
│  generate_frames()         _camera_states    live_alerts[]  │
│       │                                                      │
│  ┌────▼──────────────────────────────────────────────────┐  │
│  │              Per-Camera Generator Thread               │  │
│  │                                                        │  │
│  │  cv2.VideoCapture ──► YOLOv8.track() ──► Sliding      │  │
│  │                                          Window Algo   │  │
│  │                              │                │        │  │
│  │                         ANPR (anpr.py)  Alert Logic    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  SQLAlchemy ORM ──► SQLite (instance/alerts.db)             │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

**Stopped-vehicle detection** uses a *size-normalised* sliding-window approach rather than a raw pixel threshold. This ensures a vehicle at 200px away and 800px away are judged by the same relative movement standard — far more robust across camera zoom levels.

**Per-camera YOLO instances** are lazy-initialised. Each camera gets its own model object and tracking state (track_history, active_alerts, plate_cache). This prevents ID collisions across cameras.

**ANPR is triggered once** per stopped-vehicle event and cached — the `plate_cache` dict prevents re-running OCR on every subsequent frame.

---

## Project Structure

```
traffic_monitor/
├── app.py                  # Flask app, routes, frame generator
├── anpr.py                 # ANPR module (EasyOCR)
├── requirements.txt        # Pinned Python dependencies
├── yolov8n.pt              # YOLOv8 nano weights (place here)
│
├── templates/
│   ├── index.html          # Live dashboard
│   └── history.html        # Paginated alert log
│
├── instance/
│   └── alerts.db           # SQLite DB (auto-created)
│
└── videos/                 # (optional) store source videos here
    ├── british_highway_traffic.mp4
    └── 15 minutes of heavy traffic noise in India _ 14-08-2022.mp4
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- pip

### 2. Clone / copy the project

```bash
git clone https://github.com/your-org/traffic-iq.git
cd traffic-iq
```

### 3. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note (CPU-only):** Replace `torch>=2.2.0` in requirements.txt with the CPU build:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
> ```

### 5. Add your video files

Place your `.mp4` files in the project root (or update `CAMERAS` paths in `app.py`).

### 6. Run in development mode

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Configuration

All tunables are constants at the top of `app.py`:

| Constant | Default | Description |
|---|---|---|
| `STOPPED_TIME_THRESHOLD` | `10.0` | Seconds before a non-moving vehicle triggers an alert |
| `MOVEMENT_RATIO_THRESHOLD` | `0.12` | Allowed movement as a fraction of vehicle size |
| `HISTORY_WINDOW` | `11.0` | Sliding window length in seconds |
| `MODEL_PATH` | `yolov8n.pt` | Path to YOLO weights file |
| `MAX_LIVE_ALERTS` | `100` | Maximum alerts kept in memory |
| `CAMERAS` | (list) | Camera IDs, names, and source paths |

---


---

## Roadmap / Enhancement Ideas

These additions would significantly increase the project's value:

### 🔴 High Impact
- **Speed estimation** — Using homography (4 road reference points → real-world coords) to convert pixel displacement to km/h with correct scale.
- **Wrong-way detection** — Track the dominant flow direction per lane; flag any vehicle moving against it.
- **Vehicle counting & flow rate** — Count vehicles crossing a virtual line; display PCU/hour graph.

### 🟡 Medium Impact
- **Redis pub/sub alert bus** — Replace the in-memory list with Redis to support multi-worker deployments and WebSocket push (no polling).
- **Heatmap overlay** — Accumulate vehicle centroid positions into an OpenCV heatmap and render it as a translucent layer over the feed.
- **Multi-class alert thresholds** — Allow different stopped-time thresholds for trucks vs. motorcycles.
- **Plate blocklist / watchlist** — Cross-reference detected plates against a SQLite lookup table; fire a priority alert on a match.

### 🟢 Nice to Have
- **REST API + API key auth** — Expose alerts and stats as a proper REST API so external systems (city dashboards, police systems) can subscribe.
- **Email / Telegram / WhatsApp alert forwarding** — Push critical alerts outside the browser.
- **CSV / PDF report export** — One-click download of the alert history in tabular format.
- **Configurable UI via `.env`** — Move camera definitions, thresholds, and DB path to an environment file.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Video file not found` | Check `CAMERAS[*]["source"]` paths in `app.py`; use absolute paths if needed |
| `YOLO model not found` | Download: `from ultralytics import YOLO; YOLO("yolov8n.pt")` (auto-downloads) |
| `EasyOCR slow` | Normal on first run; model downloads ~200 MB. Set `gpu=True` if CUDA is available |
| Feed freezes | Increase `--timeout` in Gunicorn; check CPU headroom with `htop` |
| Port already in use | `lsof -i :5000` then `kill <PID>` |
| `sqlite3.OperationalError` | Ensure `instance/` directory exists; `mkdir -p instance` |
