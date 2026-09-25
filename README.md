# Road Damage Detection — INT422 Project

**Course:** INT422 (Deep Learning) | **Due:** 12-10-2026 | **Marks:** 30

## What's included
- `Road_Damage_Detection_Colab.ipynb` — full training pipeline (dataset prep, YOLOv8 training, evaluation, inference, export). Run this in Google Colab with GPU.
- `webapp/` — one Flask app that serves both:
  - **Website** (`/`) — public landing page explaining the project (`templates/landing.html`)
  - **App** (`/app`) — the working detector, also installable as a PWA on iOS/Android (`templates/index.html`, `static/manifest.json`, `static/sw.js`)
  - `app.py` — backend
  - `requirements.txt`
- `mobile_flutter/` — a real native Android/iOS app project (Flutter) that calls the same Flask API. See `mobile_flutter/README.md` to build an actual `.apk`/`.ipa`.

## Two ways to get a "mobile app"

**A. PWA (fastest, no app store, works today)**
Open the deployed site on a phone browser (`/app`):
- **Android/Chrome:** an "Install" banner appears automatically — tap it, the app installs to the home screen with its own icon, runs full-screen.
- **iOS/Safari:** tap Share → "Add to Home Screen" (a banner in-app reminds you). No App Store needed.

**B. Native Flutter app (real .apk/.ipa for submission)**
`mobile_flutter/` is a buildable Flutter project — camera/gallery picker, calls your Flask `/detect` endpoint, shows the same severity-scored results. Requires Flutter SDK installed locally (this sandbox can't compile mobile binaries). Follow `mobile_flutter/README.md`.

## How to run end-to-end

### Step 1 — Train in Colab
1. Upload `Road_Damage_Detection_Colab.ipynb` to https://colab.research.google.com
2. Runtime → Change runtime type → GPU (T4)
3. Get the RDD2022 dataset (India subset recommended for real-world relevance): https://github.com/sekilab/RoadDamageDetector
   - Easiest: search "RDD2022 YOLO" on Roboflow Universe for a pre-converted version
4. Run all cells. Training ~30-60 min for 50 epochs on yolov8n with T4 GPU.
5. Download `best.pt` at the end (last cell does this automatically).

### Step 2 — Run the web app locally
```bash
cd webapp
pip install -r requirements.txt
python app.py
```
On first startup, the app downloads the YOLOv8 road-damage checkpoint from `nsr51324/Road_Damage_Object_Detection` on Hugging Face. An internet connection is needed for that initial download. To use a local compatible checkpoint instead, set `MODEL_PATH` before starting Flask. Open http://localhost:5000 and upload a road photo to see detected damage with confidence and severity.

The selected model card reports YOLOv8 mAP50 of 0.394 and mAP50-95 of 0.230. Treat detections as an inspection aid: this lightweight checkpoint can miss damage or produce false positives and is not a substitute for professional road-safety assessment.

### User accounts and admin activity
- The detector requires an account. Users can register from `/login`; new registrations always receive the `user` role.
- Configure `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first server start to create the administrator account. This account can review accounts and recent login, detector, dataset, and accident-data activity at `/admin`. Admin accounts cannot be created from the public registration form.
- Set `SECRET_KEY` to a long, random value and keep it stable across restarts. Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS.
- SQLite is stored at `webapp/data/roadscan.sqlite3` by default. Set `DATABASE_PATH` to a persistent volume path when deploying to a host with an ephemeral filesystem; otherwise account and audit data can be lost on redeploy.
- The audit log records timestamps, account email, action, client label, IP address, browser/device user-agent, and detection count/classes/mode. It does not store uploaded image contents. Restrict access to the database and admin account because IP and device details are personal data.
- The Flutter app uses the same accounts and API. Set its `SERVER_URL` to the deployed server URL when building/running it. Mobile API tokens expire after 30 days; the app asks the user to sign in again after it is closed.

### Step 3 (optional) — "Real life" deployment
- Deploy Flask app to Render/Railway/PythonAnywhere (free tiers) for a live URL to include in your submission.
- For a "mobile app" without native development: the web app above is already mobile-responsive and can be opened from a phone browser to snap and upload road photos — this satisfies "app" requirement without needing Android/iOS build tools.
- Add a Google Maps/Leaflet.js page that plots reported damage locations (use browser geolocation API when photo is uploaded) for a stronger "real-life civic reporting" angle — ask if you want this added.

## Report structure (for the 30-mark submission)
1. Abstract
2. Introduction & Motivation (road safety, maintenance cost, manual inspection limitations)
3. Literature Review (RDD2022 challenge papers, YOLO-based detection works)
4. Dataset description (RDD2022, classes D00/D10/D20/D40, train/val split)
5. Methodology (YOLOv8 architecture, training config, severity scoring logic)
6. Implementation (Colab pipeline + Flask app architecture diagram)
7. Results (mAP50, mAP50-95, precision/recall, sample detection images)
8. Real-world application (municipal reporting workflow, deployment plan)
9. Conclusion & Future Work (video/live-feed detection, GPS-tagged damage map, mobile app)
10. References
