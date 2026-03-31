"""
app.py – Traffic Intelligence Monitor
Flask + YOLOv8 multi-camera vehicle tracking with stopped-vehicle detection & ANPR.
"""

import cv2
import os
import time
import math
import datetime
import numpy as np
from collections import defaultdict

from flask import Flask, render_template, Response, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from ultralytics import YOLO

try:
    from anpr import initialize_anpr, get_plate_from_frame
except ImportError:
    print("[WARN] anpr.py not found – ANPR disabled.")
    def initialize_anpr(): return False
    def get_plate_from_frame(frame, box): return "ANPR_OFF"


# ── Configuration ──────────────────────────────────────────────────────────────

CAMERAS = [
    {"id": 0, "name": "Tunnel Entrance",   "source": "videos/stock.mp4"},
    {"id": 1, "name": "Flyover Exit",      "source": "videos/british_highway_traffic.mp4"},
    {"id": 2, "name": "India Highway",     "source": "videos/"
    "15 minutes of heavy traffic noise in India _ 14-08-2022.mp4"},
]

MODEL_PATH             = "yolov8n.pt"
VEHICLE_CLASSES        = {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}

# Stopped-vehicle detection tunables
STOPPED_TIME_THRESHOLD = 10.0   # seconds a vehicle must be still to trigger alert
MOVEMENT_RATIO_THRESHOLD = 0.12 # movement / diagonal_size  (normalised)
HISTORY_WINDOW         = STOPPED_TIME_THRESHOLD + 1.0  # sliding window (s)

# Render style
FONT            = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE      = 0.65
FONT_THICKNESS  = 2
BOX_THICKNESS   = 2
MAX_LIVE_ALERTS = 100


# ── Flask / DB setup ───────────────────────────────────────────────────────────

basedir = os.path.abspath(os.path.dirname(__file__))

db_path = os.path.join(basedir, "instance", "alerts.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class AlertLog(db.Model):
    id           = db.Column(db.Integer,  primary_key=True)
    timestamp    = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    camera_name  = db.Column(db.String(60))
    event_type   = db.Column(db.String(40))
    vehicle_id   = db.Column(db.Integer)
    plate        = db.Column(db.String(20))
    details      = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id":          self.id,
            "timestamp":   self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "camera_name": self.camera_name,
            "event_type":  self.event_type,
            "vehicle_id":  self.vehicle_id,
            "plate":       self.plate,
            "details":     self.details,
        }


def _log_alert(cam_name: str, event_type: str, vid: int, plate: str, details: str):
    """Thread-safe DB insert (called from generator threads)."""
    with app.app_context():
        try:
            db.session.add(AlertLog(
                camera_name=cam_name, event_type=event_type,
                vehicle_id=vid, plate=plate, details=details
            ))
            db.session.commit()
        except Exception as exc:
            print(f"[DB] Write error: {exc}")
            db.session.rollback()


# ── Per-camera state ───────────────────────────────────────────────────────────

_camera_states: dict = {}
live_alerts: list    = []   # newest-first, capped at MAX_LIVE_ALERTS


def _get_cam_state(cam_id: int) -> dict:
    """Lazy-init per-camera YOLO model and tracking state."""
    if cam_id not in _camera_states:
        print(f"[INFO] Initialising YOLO for camera {cam_id} …")
        try:
            model = YOLO(MODEL_PATH)
        except Exception as exc:
            print(f"[ERROR] YOLO load failed for cam {cam_id}: {exc}")
            model = None

        _camera_states[cam_id] = {
            "model":          model,
            # tid → [(t, cx, cy, diagonal)]
            "track_history":  defaultdict(list),
            # set of "STOP-{tid}" strings
            "active_alerts":  set(),
            # tid → plate string
            "plate_cache":    {},
            # live stats
            "vehicle_count":  0,
            "stopped_count":  0,
        }
    return _camera_states[cam_id]


# ── Core frame generator ───────────────────────────────────────────────────────

def _generate_frames(cam_id: int):
    cfg   = next((c for c in CAMERAS if c["id"] == cam_id), None)
    if not cfg:
        return

    source = cfg["source"]
    if isinstance(source, str) and not os.path.exists(source):
        print(f"[WARN] {source} not found – falling back to webcam 0.")
        source = 0

    cap   = cv2.VideoCapture(source)
    state = _get_cam_state(cam_id)
    model         = state["model"]
    track_history = state["track_history"]
    active_alerts = state["active_alerts"]
    plate_cache   = state["plate_cache"]

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            # loop video
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            track_history.clear()
            active_alerts.clear()
            plate_cache.clear()
            continue

        now = time.time()
        state["vehicle_count"] = 0
        state["stopped_count"] = 0

        if model:
            results = model.track(
                frame, persist=True,
                classes=list(VEHICLE_CLASSES.keys()),
                verbose=False
            )

            boxes, ids, clss = [], [], []
            if results and results[0].boxes and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                ids   = results[0].boxes.id.int().cpu().tolist()
                clss  = results[0].boxes.cls.int().cpu().tolist()

            current_ids = set(ids)
            state["vehicle_count"] = len(current_ids)

            for (x1, y1, x2, y2), tid, cid in zip(boxes, ids, clss):
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                diag   = math.hypot(x2 - x1, y2 - y1)

                # ── Sliding-window history ──
                hist = track_history[tid]
                hist.append((now, cx, cy, diag))
                hist[:] = [h for h in hist if (now - h[0]) <= HISTORY_WINDOW]

                is_stopped   = False
                status_color = (0, 200, 80)   # green

                if len(hist) > 1:
                    t0, ox, oy, od = hist[0]
                    dt = now - t0
                    if dt >= STOPPED_TIME_THRESHOLD:
                        dist  = math.hypot(cx - ox, cy - oy)
                        avg_d = (diag + od) / 2 or 1.0
                        if (dist / avg_d) < MOVEMENT_RATIO_THRESHOLD:
                            is_stopped   = True
                            status_color = (0, 40, 220)  # red

                cls_name = VEHICLE_CLASSES.get(cid, "Vehicle")
                label    = f"{cls_name} #{tid}"

                if is_stopped:
                    state["stopped_count"] += 1
                    label += " ⬛ STOPPED"
                    key    = f"STOP-{tid}"

                    if key not in active_alerts:
                        plate = plate_cache.setdefault(
                            tid, get_plate_from_frame(frame, (x1, y1, x2, y2))
                        )
                        msg = f"{cls_name} ID:{tid} stopped | Plate: {plate}"
                        live_alerts.insert(0, {
                            "type":    "stop",
                            "camera":  cfg["name"],
                            "cam_id":  cam_id,
                            "time":    datetime.datetime.now().strftime("%H:%M:%S"),
                            "message": msg,
                            "plate":   plate,
                        })
                        if len(live_alerts) > MAX_LIVE_ALERTS:
                            live_alerts[:] = live_alerts[:MAX_LIVE_ALERTS]

                        _log_alert(cfg["name"], "STOPPED", tid, plate, msg)
                        active_alerts.add(key)

                # Draw bounding box + label
                cv2.rectangle(frame, (x1, y1), (x2, y2), status_color, BOX_THICKNESS)
                cv2.putText(frame, label, (x1, max(y1 - 10, 12)),
                            FONT, FONT_SCALE, status_color, FONT_THICKNESS)

            # Cleanup stale tracks
            stale = {k for k in active_alerts if int(k.split("-")[1]) not in current_ids}
            active_alerts -= stale
            for tid in [t for t in track_history if t not in current_ids]:
                del track_history[tid]

        # Encode + yield MJPEG frame
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok2:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + buf.tobytes() + b"\r\n")

    cap.release()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", cameras=CAMERAS)


@app.route("/video_feed/<int:cam_id>")
def video_feed(cam_id):
    return Response(
        _generate_frames(cam_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/alerts")
def api_alerts():
    return jsonify(live_alerts)


@app.route("/api/stats")
def api_stats():
    stats = []
    for cam in CAMERAS:
        s = _camera_states.get(cam["id"], {})
        stats.append({
            "cam_id":        cam["id"],
            "name":          cam["name"],
            "vehicle_count": s.get("vehicle_count", 0),
            "stopped_count": s.get("stopped_count", 0),
        })
    total_alerts = AlertLog.query.count()
    return jsonify({"cameras": stats, "total_alerts": total_alerts})


@app.route("/history")
def history():
    page       = int(request.args.get("page", 1))
    per_page   = 50
    pagination = (AlertLog.query
                  .order_by(AlertLog.timestamp.desc())
                  .paginate(page=page, per_page=per_page, error_out=False))
    return render_template("history.html", pagination=pagination)


@app.route("/api/history")
def api_history():
    page  = int(request.args.get("page", 1))
    items = (AlertLog.query
             .order_by(AlertLog.timestamp.desc())
             .paginate(page=page, per_page=50, error_out=False))
    return jsonify({
        "alerts": [a.to_dict() for a in items.items],
        "total":  items.total,
        "pages":  items.pages,
        "page":   items.page,
    })


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    initialize_anpr()
    port = int(os.environ.get("PORT", 5000))
    print(f"[INFO] Traffic Monitor starting on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)