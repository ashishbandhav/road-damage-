"""
Road Damage Detection - Flask Web App
Run: python app.py
Requires: ultralytics, flask, opencv-python
Downloads the default road-damage checkpoint from Hugging Face on first startup.
Set MODEL_PATH to use a local compatible checkpoint instead.
"""
from flask import Flask, request, render_template, jsonify, send_from_directory, abort, session, g, redirect, url_for

try:
    from ultralytics import YOLO
except (ImportError, OSError):
    YOLO = None
try:
    from huggingface_hub import hf_hub_download
except ImportError:
    hf_hub_download = None
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from contextlib import contextmanager
import hashlib, json, secrets, sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
import csv, os, uuid, cv2
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true",
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
)
UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
DATABASE_PATH = os.getenv(
    "DATABASE_PATH", os.path.join(os.path.dirname(__file__), "data", "roadscan.sqlite3")
)
os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS access_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                email TEXT,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                client TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            );
        """)
        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            connection.execute(
                "INSERT OR IGNORE INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                (admin_email, generate_password_hash(admin_password), datetime.now(timezone.utc).isoformat()),
            )


def record_activity(user, action, details=None):
    with database() as connection:
        connection.execute(
            "INSERT INTO activity_logs (user_id, email, action, details, client, ip_address, user_agent, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user["id"] if user else None,
                user["email"] if user else None,
                action,
                json.dumps(details or {}, separators=(",", ":")),
                request.headers.get("X-Client-Platform", "web")[:40],
                request.remote_addr,
                request.user_agent.string[:300],
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def issue_access_token(user_id):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with database() as connection:
        connection.execute(
            "INSERT INTO access_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), user_id, expires_at),
        )
    return token


@app.before_request
def load_authenticated_user():
    g.user = None
    user_id = session.get("user_id")
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with database() as connection:
            row = connection.execute(
                "SELECT users.* FROM access_tokens JOIN users ON users.id = access_tokens.user_id WHERE token_hash = ? AND expires_at > ?",
                (token_hash, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
        if row:
            g.user = row
            return
    if user_id:
        with database() as connection:
            g.user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Administrator access required"}), 403
            abort(403)
        return view(*args, **kwargs)
    return wrapped


initialize_database()

MODEL_REPO = "nsr51324/Road_Damage_Object_Detection"
MODEL_FILENAME = "runs/detect/yolov8_road/weights/best.pt"
MODEL_PATH = os.getenv("MODEL_PATH", "")


def load_detection_model():
    if YOLO is None:
        app.logger.warning("Ultralytics is unavailable; detection is disabled.")
        return None
    if MODEL_PATH:
        weights_path = MODEL_PATH
    elif hf_hub_download is not None:
        try:
            weights_path = hf_hub_download(
                repo_id=MODEL_REPO,
                filename=MODEL_FILENAME,
            )
        except Exception:
            app.logger.exception("Could not download the configured road-damage model.")
            return None
    else:
        app.logger.error("huggingface_hub is unavailable; detection is disabled.")
        return None
    try:
        app.logger.info("Loading road-damage model weights from %s", weights_path)
        return YOLO(weights_path)
    except Exception:
        app.logger.exception("Could not load the road-damage model weights.")
        return None


model = load_detection_model()
INCIDENT_UPDATES = deque(maxlen=30)
ACCIDENTS_CSV_PATH = os.getenv(
    "ACCIDENTS_CSV_PATH",
    os.path.join(os.path.dirname(__file__), "data", "accidents.csv"),
)
KAGGLE_DATASET = "vidishbijalwan/rdd2022-india-pothole-d40"
KAGGLE_DATASET_ROOT = os.getenv("KAGGLE_DATASET_ROOT", "")

SEVERITY_COLORS = {"Low": (0, 200, 0), "Medium": (0, 165, 255), "High": (0, 0, 255)}


def severity_from_area(area_pct):
    if area_pct > 8:
        return "High"
    elif area_pct > 3:
        return "Medium"
    return "Low"


def add_incident_updates(detections):
    now = datetime.now(timezone.utc).isoformat()
    for detection in detections:
        is_pothole = detection["class"].upper() in {"D40", "POTHOLE"}
        urgent = is_pothole and detection["severity"] == "High"
        INCIDENT_UPDATES.appendleft({
            "id": uuid.uuid4().hex,
            "time": now,
            "type": "Emergency hazard" if urgent else "Road damage reported",
            "class": detection["class"],
            "severity": detection["severity"],
            "message": "Urgent pothole risk: notify emergency road crews." if urgent else "New road damage detected and queued for inspection.",
            "urgent": urgent,
        })


def read_accident_data():
    if not os.path.exists(ACCIDENTS_CSV_PATH):
        return {"error": "Accident CSV file was not found."}

    with open(ACCIDENTS_CSV_PATH, newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))

    def number(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    fields = {
        "2020": ("2020 - Number of Accidents", "2020 - Number of Fatalities"),
        "2021": ("2021 - Number of Accidents", "2021 - Number of Fatalities"),
        "2022": ("2022 - Number of Accidents", "2022 - Number of Fatalities"),
    }
    records = []
    total_row = next((row for row in rows if row.get("State/UT") == "Total"), None)
    for row in rows:
        if row.get("State/UT") == "Total":
            continue
        records.append({
            "state": row.get("State/UT", ""),
            "accidents": {year: number(row.get(accidents)) for year, (accidents, _) in fields.items()},
            "fatalities": {year: number(row.get(fatalities)) for year, (_, fatalities) in fields.items()},
        })

    summary = {}
    for year, (accidents, fatalities) in fields.items():
        summary[year] = {
            "accidents": number(total_row.get(accidents)) if total_row else sum(item["accidents"][year] or 0 for item in records),
            "fatalities": number(total_row.get(fatalities)) if total_row else sum(item["fatalities"][year] or 0 for item in records),
        }
    return {"source": os.path.basename(ACCIDENTS_CSV_PATH), "summary": summary, "records": records}


def kaggle_dataset_root():
    if KAGGLE_DATASET_ROOT and os.path.isdir(KAGGLE_DATASET_ROOT):
        return KAGGLE_DATASET_ROOT
    try:
        import kagglehub
        return kagglehub.dataset_download(KAGGLE_DATASET)
    except Exception:
        return None


def kaggle_image_files():
    root = kaggle_dataset_root()
    if not root:
        return None, [], None
    image_dir = os.path.join(root, "train", "images")
    if not os.path.isdir(image_dir):
        image_dir = os.path.join(root, "versions", "1", "train", "images")
    if not os.path.isdir(image_dir):
        return root, [], None
    files = sorted(
        path for path in os.listdir(image_dir)
        if path.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    return root, files, image_dir


def kaggle_annotation_detections(filename, width, height):
    root = kaggle_dataset_root()
    if not root:
        return None
    version_root = root if os.path.isdir(os.path.join(root, "train")) else os.path.join(root, "versions", "1")
    annotation_path = os.path.join(version_root, "train", "annotations", "xmls", f"{os.path.splitext(filename)[0]}.xml")
    if not os.path.exists(annotation_path):
        return None

    annotation = ET.parse(annotation_path).getroot()
    source_width = int(annotation.findtext("size/width", str(width)))
    source_height = int(annotation.findtext("size/height", str(height)))
    scale_x = width / source_width
    scale_y = height / source_height
    detections = []
    for item in annotation.findall("object"):
        box = item.find("bndbox")
        if box is None:
            continue
        x1 = round(float(box.findtext("xmin", "0")) * scale_x)
        y1 = round(float(box.findtext("ymin", "0")) * scale_y)
        x2 = round(float(box.findtext("xmax", "0")) * scale_x)
        y2 = round(float(box.findtext("ymax", "0")) * scale_y)
        area_pct = ((x2 - x1) * (y2 - y1)) / (width * height) * 100
        detections.append({
            "class": item.findtext("name", "unknown"),
            "confidence": 1.0,
            "severity": severity_from_area(area_pct),
            "bbox": [x1, y1, x2, y2],
            "source": "Kaggle XML annotation",
        })
    return detections


def create_user(email, password):
    email = email.strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        return None, "Enter a valid email address."
    if len(password) < 8:
        return None, "Password must be at least 8 characters."
    try:
        with database() as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
                (email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
            )
            return connection.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone(), None
    except sqlite3.IntegrityError:
        return None, "An account with that email already exists."


def auth_response(user, token):
    return jsonify({
        "access_token": token,
        "user": {"email": user["email"], "role": user["role"]},
    })


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("admin_dashboard" if g.user["role"] == "admin" else "index"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with database() as connection:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            record_activity(user, "login")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "index"))
        record_activity(None, "login_failed", {"email": email})
        error = "Email or password is incorrect."
    return render_template("auth.html", mode="login", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        user, error = create_user(request.form.get("email", ""), request.form.get("password", ""))
        if user:
            session.clear()
            session["user_id"] = user["id"]
            record_activity(user, "account_created")
            return redirect(url_for("index"))
    return render_template("auth.html", mode="register", error=error)


@app.post("/logout")
@login_required
def logout():
    record_activity(g.user, "logout")
    session.clear()
    return redirect(url_for("home"))


@app.post("/api/auth/register")
def api_register():
    data = request.get_json(silent=True) or {}
    user, error = create_user(str(data.get("email", "")), str(data.get("password", "")))
    if error:
        return jsonify({"error": error}), 400
    token = issue_access_token(user["id"])
    record_activity(user, "account_created")
    return auth_response(user, token), 201


@app.post("/api/auth/login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    with database() as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        record_activity(None, "login_failed", {"email": email})
        return jsonify({"error": "Email or password is incorrect."}), 401
    token = issue_access_token(user["id"])
    record_activity(user, "login")
    return auth_response(user, token)


@app.post("/api/auth/logout")
@login_required
def api_logout():
    record_activity(g.user, "logout")
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with database() as connection:
            connection.execute("DELETE FROM access_tokens WHERE token_hash = ?", (token_hash,))
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
@login_required
def api_current_user():
    return jsonify({"user": {"email": g.user["email"], "role": g.user["role"]}})


@app.route("/")
def home():
    return render_template("landing.html")


@app.route("/app")
@login_required
def index():
    record_activity(g.user, "detector_opened")
    return render_template("index.html", detector_ready=model is not None)


@app.route("/api/updates")
@login_required
def updates():
    return jsonify({"updates": list(INCIDENT_UPDATES)})


@app.route("/api/accidents")
@login_required
def accidents():
    record_activity(g.user, "accident_data_viewed")
    data = read_accident_data()
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data)


@app.route("/api/kaggle-dataset")
@login_required
def kaggle_dataset():
    record_activity(g.user, "sample_dataset_viewed")
    root, files, _ = kaggle_image_files()
    if not root:
        return jsonify({"error": "Kaggle dataset is unavailable. Run kagglehub setup first."}), 503
    return jsonify({
        "dataset": KAGGLE_DATASET,
        "split": "train",
        "image_count": len(files),
        "sample": [
            {"name": name, "url": f"/kaggle-image/train/{name}"}
            for name in files[:12]
        ],
    })


@app.route("/kaggle-image/<split>/<filename>")
@login_required
def kaggle_image(split, filename):
    if split != "train" or os.path.basename(filename) != filename:
        abort(404)
    root, files, image_dir = kaggle_image_files()
    if not root or not image_dir or filename not in files:
        abort(404)
    return send_from_directory(image_dir, filename)


@app.route("/detect", methods=["POST"])
@login_required
def detect():
    fname = f"{uuid.uuid4().hex}.jpg"
    in_path = os.path.join(UPLOAD_DIR, fname)
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        file = request.files["image"]
        original_name = secure_filename(file.filename or "")
        file.save(in_path)

        img = cv2.imread(in_path)
        if img is None:
            return jsonify({"error": "Unable to read uploaded image"}), 400

        h, w = img.shape[:2]
        detections = []

        detection_mode = "model"
        if model is None:
            annotated_detections = kaggle_annotation_detections(original_name, w, h)
            detection_mode = "kaggle_annotations" if annotated_detections is not None else "no_model"
            for detection in annotated_detections or []:
                x1, y1, x2, y2 = detection["bbox"]
                cls_name = detection["class"]
                conf = detection["confidence"]
                sev = detection["severity"]
                color = SEVERITY_COLORS[sev]
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                label = f"{cls_name} {conf:.2f} [{sev}]"
                cv2.putText(img, label, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                detections.append(detection)
        else:
            results = model.predict(source=in_path, conf=0.35, verbose=False)[0]
            for box in results.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_name = results.names[int(box.cls[0])]
                conf = float(box.conf[0])
                area_pct = ((x2 - x1) * (y2 - y1)) / (w * h) * 100
                sev = severity_from_area(area_pct)
                color = SEVERITY_COLORS[sev]
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                label = f"{cls_name} {conf:.2f} [{sev}]"
                cv2.putText(img, label, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                detections.append({
                    "class": cls_name, "confidence": round(conf, 2),
                    "severity": sev, "bbox": [x1, y1, x2, y2]
                })

        out_name = f"result_{fname}"
        out_path = os.path.join(RESULT_DIR, out_name)
        if not cv2.imwrite(out_path, img):
            raise OSError("Could not save the annotated result image")
        add_incident_updates(detections)
        record_activity(g.user, "detection_completed", {
            "count": len(detections),
            "classes": sorted({item["class"] for item in detections}),
            "mode": detection_mode,
        })

        return jsonify({
            "detections": detections,
            "count": len(detections),
            "mode": detection_mode,
            "message": "Exact Kaggle XML annotations used." if detection_mode == "kaggle_annotations" else "No trained model is installed; no pothole size was fabricated." if detection_mode == "no_model" else "YOLO model detections used.",
            "result_image": f"/{out_path}"
        })
    except RequestEntityTooLarge:
        return jsonify({"error": "Image is too large. Upload an image smaller than 12 MB."}), 413
    except Exception:
        app.logger.exception("Road-damage image processing failed")
        return jsonify({"error": "The server could not process this image. Try a smaller JPG or PNG, then check the service logs if it continues."}), 500
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)


@app.errorhandler(413)
def request_too_large(error):
    if request.path == "/detect":
        return jsonify({"error": "Image is too large. Upload an image smaller than 12 MB."}), 413
    return error


@app.get("/admin")
@admin_required
def admin_dashboard():
    with database() as connection:
        users = connection.execute(
            "SELECT users.email, users.role, users.created_at, "
            "MAX(CASE WHEN activity_logs.action = 'login' THEN activity_logs.created_at END) AS last_login, "
            "SUM(CASE WHEN activity_logs.action = 'detection_completed' THEN 1 ELSE 0 END) AS detections "
            "FROM users LEFT JOIN activity_logs ON activity_logs.user_id = users.id "
            "GROUP BY users.id ORDER BY users.created_at DESC"
        ).fetchall()
        events = connection.execute(
            "SELECT email, action, details, client, ip_address, user_agent, created_at "
            "FROM activity_logs ORDER BY id DESC LIMIT 500"
        ).fetchall()
    return render_template("admin.html", users=users, events=events)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
