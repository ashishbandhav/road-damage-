import os
from collections import Counter

import spaces
from huggingface_hub import hf_hub_download
from PIL import Image
from ultralytics import YOLO
import gradio as gr


MODEL_REPO = "nsr51324/Road_Damage_Object_Detection"
MODEL_FILE = "runs/detect/yolov8_road/weights/best.pt"
ZERO_GPU_ENABLED = os.getenv("SPACES_ZERO_GPU") == "1"

weights_path = hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILE)
model = YOLO(weights_path)
if ZERO_GPU_ENABLED:
    model.to("cuda")


@spaces.GPU(duration=30)
def detect_damage(
    image: Image.Image | None,
    confidence: float,
) -> tuple[Image.Image | None, str, list[list[str | float]]]:
    """Detect road damage in an uploaded image and return its annotated image and boxes.

    Args:
        image: Road image uploaded by the visitor.
        confidence: Minimum model confidence threshold from 0.05 to 0.90.
    """
    if image is None:
        raise gr.Error("Upload a road image before running detection.")

    result = model.predict(
        source=image.convert("RGB"),
        conf=float(confidence),
        imgsz=640,
        verbose=False,
    )[0]
    annotated_rgb = result.plot()[:, :, ::-1].copy()
    annotated_image = Image.fromarray(annotated_rgb)
    boxes = result.boxes

    if boxes is None or len(boxes) == 0:
        return annotated_image, "No damage detected above the selected confidence threshold.", []

    rows: list[list[str | float]] = []
    classes: list[str] = []
    for box in boxes:
        class_name = str(model.names[int(box.cls.item())])
        score = round(float(box.conf.item()), 4)
        x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
        rows.append([class_name, score, f"{x1}, {y1}, {x2}, {y2}"])
        classes.append(class_name)

    counts = Counter(classes)
    summary_lines = [f"**{len(rows)} damage instance(s) detected**", ""]
    summary_lines.extend(f"- {name}: {count}" for name, count in sorted(counts.items()))
    summary_lines.append("\nReview the marked image; this model can miss damage or return false positives.")
    return annotated_image, "\n".join(summary_lines), rows


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; }
.dark .gradio-container { color: #f2f0e8 !important; background: #17191b !important; }
.gradio-container { font-family: 'Inter', sans-serif; }
.app-header { border-top: 5px solid #f5b400; padding: 22px 4px 16px; margin-bottom: 12px; }
.app-kicker { color: #f5b400; font: 11px 'IBM Plex Mono', monospace; letter-spacing: 1px; text-transform: uppercase; }
.app-title { color: #f2f0e8; font: 800 36px 'Barlow Condensed', sans-serif; text-transform: uppercase; margin: 5px 0; }
.app-subtitle { color: #a4a7ab; max-width: 720px; line-height: 1.55; }
.section-label { color: #f5b400; font: 11px 'IBM Plex Mono', monospace; text-transform: uppercase; }
footer { display: none !important; }
"""


with gr.Blocks(
    title="RoadScan Damage Detector",
) as demo:
    gr.HTML(
        """
        <header class="app-header">
          <div class="app-kicker">RoadScan / Infrastructure inspection</div>
          <h1 class="app-title">Road damage detector</h1>
          <div class="app-subtitle">Upload a road photo to locate and classify visible damage with the selected YOLOv8 checkpoint.</div>
        </header>
        """
    )

    with gr.Row(equal_height=True):
        with gr.Column(scale=1):
            gr.Markdown("#### 01 / Road image", elem_classes=["section-label"])
            image_input = gr.Image(
                label="Upload image",
                type="pil",
                sources=["upload", "webcam"],
                height=420,
            )
            confidence_input = gr.Slider(
                minimum=0.05,
                maximum=0.90,
                value=0.25,
                step=0.05,
                label="Minimum confidence",
            )
            run_button = gr.Button("Run inspection", variant="primary")

        with gr.Column(scale=1):
            gr.Markdown("#### 02 / Annotated result", elem_classes=["section-label"])
            output_image = gr.Image(label="Damage marks", type="pil", height=420)

    summary_output = gr.Markdown(label="Detection summary")
    detections_output = gr.Dataframe(
        headers=["Damage class", "Confidence", "Box (x1, y1, x2, y2)"],
        datatype=["str", "number", "str"],
        label="Detected objects",
        interactive=False,
    )
    gr.Markdown(
        "Model: [nsr51324/Road_Damage_Object_Detection](https://huggingface.co/nsr51324/Road_Damage_Object_Detection) "
        "| YOLOv8 mAP50: 0.394. Results are an inspection aid, not a safety certification."
    )

    run_button.click(
        fn=detect_damage,
        inputs=[image_input, confidence_input],
        outputs=[output_image, summary_output, detections_output],
        api_name="detect_damage",
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        theme=gr.themes.Citrus(),
        css=CSS,
    )