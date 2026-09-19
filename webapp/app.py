"""
Road Damage Detection - Flask Web App
Run: python app.py
Requires: ultralytics, flask, opencv-python
Put your trained model as 'best.pt' in this folder (from the Colab notebook).
"""
from flask import Flask, request, render_template, jsonify, send_from_directory, abort
from ultralytics import YOLO
from collections import deque
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
import csv, os, uuid, cv2
import xml.etree.ElementTree as ET

app = Flask(__name__)
UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

MODEL_PATH = "best.pt"  # replace with your trained weights
model = YOLO(MODEL_PATH) if os.path.exists(MODEL_PATH) else None
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


@app.route("/")
def home():
    return render_template("landing.html")


@app.route("/app")
def index():
    return render_template("index.html")


@app.route("/api/updates")
def updates():
    return jsonify({"updates": list(INCIDENT_UPDATES)})


@app.route("/api/accidents")
def accidents():
    data = read_accident_data()
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data)


@app.route("/api/kaggle-dataset")
def kaggle_dataset():
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
def kaggle_image(split, filename):
    if split != "train" or os.path.basename(filename) != filename:
        abort(404)
    root, files, image_dir = kaggle_image_files()
    if not root or not image_dir or filename not in files:
        abort(404)
    return send_from_directory(image_dir, filename)


@app.route("/detect", methods=["POST"])
def detect():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    original_name = secure_filename(file.filename or "")
    fname = f"{uuid.uuid4().hex}.jpg"
    in_path = os.path.join(UPLOAD_DIR, fname)
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
    cv2.imwrite(out_path, img)
    add_incident_updates(detections)

    return jsonify({
        "detections": detections,
        "count": len(detections),
        "mode": detection_mode,
        "message": "Exact Kaggle XML annotations used." if detection_mode == "kaggle_annotations" else "No trained model is installed; no pothole size was fabricated." if detection_mode == "no_model" else "YOLO model detections used.",
        "result_image": f"/{out_path}"
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
