# RoadScan AI — Flutter Mobile App

Native Android/iOS app that calls the same Flask backend as the web app.

## Setup

1. Install Flutter SDK: https://docs.flutter.dev/get-started/install
2. Create the project skeleton and drop in these files:
   ```bash
   flutter create roadscan_ai
   cd roadscan_ai
   # replace lib/main.dart with the provided main.dart
   # replace pubspec.yaml with the provided pubspec.yaml
   flutter pub get
   ```
3. **Important:** open `lib/main.dart` and set `SERVER_URL` to your running Flask server:
   - Testing on your PC + physical phone on the current WiFi: use `http://10.17.149.65:5000`
   - Testing on an emulator: Android emulator uses `http://10.0.2.2:5000` to reach your host machine
   - Production: your deployed URL (Render/Railway), e.g. `https://roadscan.onrender.com`

4. Run:
   ```bash
   flutter run
   ```

5. Build a real installable file for your project submission:
   ```bash
   flutter build apk --release      # Android .apk
   flutter build ios --release      # iOS (requires Mac + Xcode + Apple dev account)
   ```

## Permissions
Android needs camera + internet permissions — Flutter's `image_picker` plugin adds these automatically when you run `flutter create`. For iOS, add to `ios/Runner/Info.plist`:
```xml
<key>NSCameraUsageDescription</key>
<string>Used to capture road photos for damage detection</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>Used to select road photos for damage detection</string>
```

## What it does
- Take a photo or pick from gallery
- Sends it to your Flask `/detect` endpoint (the same model as the web app)
- Displays the annotated result image + a list of detections with severity (Low/Medium/High)
