---
title: RoadScan Damage Detector
emoji: 🛣️
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 6.28.0
app_file: app.py
short_description: Upload road photos and inspect detected damage.
python_version: "3.12"
startup_duration_timeout: 30m
---

# RoadScan Damage Detector

Upload a road image to view YOLOv8 damage detections, confidence scores, and an annotated result image.

The app uses the `runs/detect/yolov8_road/weights/best.pt` checkpoint from [nsr51324/Road_Damage_Object_Detection](https://huggingface.co/nsr51324/Road_Damage_Object_Detection), downloaded on startup from the Hugging Face Hub. The model card reports mAP50 of 0.394 and mAP50-95 of 0.230. It can miss damage or produce false positives; do not treat its output as a professional road-safety assessment.

## Run locally

Install the app dependencies and the Space runtime packages, then launch the demo:

```bash
pip install -r requirements.txt gradio==6.28.0 spaces
python app.py
```

Open `http://127.0.0.1:7860`. The first launch needs internet access to download the checkpoint.

## Hugging Face hosting

This app supports ZeroGPU. Create the Space with the `zero-a10g` flavor, then upload the contents of this folder as a Space repository. ZeroGPU eligibility and quotas depend on the Hugging Face account. The app also works on paid CPU or GPU Gradio Space hardware.