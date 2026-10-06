import signal
import sys
import cv2
import time
from ultralytics import YOLO
from usb_controller import XRPController

# Flag to handle clean shutdown on Ctrl+C
running = True


def signal_handler(sig, frame):
    global running
    print("\nStopping capture and saving video...")
    running = False


signal.signal(signal.SIGINT, signal_handler)

# Load model (e.g., yolo11n.pt or yolov8n.pt)
model = YOLO("yolo11n.pt")

# Camera setup (try 1 or 2 if index 0 is not the right USB camera)
camera_index = 0
cap = cv2.VideoCapture(camera_index)

if not cap.isOpened():
    print(f"Error: Could not open camera at index {camera_index}")
    sys.exit(1)

# Retrieve camera properties
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

# Fallback FPS if the camera driver returns 0 or an invalid number
if fps <= 0:
    fps = 30.0

# Standard container rate that Totem/GStreamer respects
CONTAINER_FPS = 30.0
TARGET_RATE = 2.0  # 2 updates per second
REPEAT_COUNT = int(CONTAINER_FPS / TARGET_RATE)  # 15 writes per capture
FRAME_INTERVAL = 1.0 / TARGET_RATE  # 0.5 seconds cadence
    
output_filename = "annotated_output.mp4"

# Set up VideoWriter
# 'mp4v' is widely compatible; use 'avc1' or 'X264' if supported by your ffmpeg/OpenCV build
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

# --- Bottom-Left Layout Coordinates ---
box_width = 200
box_height = 80
margin = 15

# Box top-left: (x1, y1), bottom-right: (x2, y2)
x1 = margin
y1 = height - margin - box_height
x2 = margin + box_width
y2 = height - margin

# Text baselines positioned inside the badge
line1_pos = (x1 + 10, y1 + 30)
line2_pos = (x1 + 10, y1 + 65)

print(f"Recording from camera {camera_index} ({width}x{height} @ {fps:.1f} FPS)...")
print("Press Ctrl+C in terminal to stop recording.")

frame_count = 0

def annotate_frame(frame, var1, var2):
    # Text appearance settings
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    text_color = (0, 255, 0)       # Green (BGR)
    thickness = 2

    # Draw a dark background rectangle in the bottom-left for readability
    # Coordinates: (x1, y1) to (x2, y2)
    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 0), -1)

    # Draw Variable 1
    # cv2.putText(image, text, (x_coord, y_coord), font, scale, color, thickness)
    cv2.putText(
        frame,
        var1,
        line1_pos,
        font,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )

    # Draw Variable 2 (offset y down to avoid overlap)
    cv2.putText(
        frame,
        var2,
        line2_pos,
        font,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )
    return frame

with XRPController() as bot:
    try:
        while running and cap.isOpened():
            start_time = time.time()
            
            success, frame = cap.read()
            if not success:
                print("Warning: Dropped frame or camera disconnected.")
                break

            # Run inference (verbose=False keeps headless logs clean)
            results = model(frame, conf=0.5, verbose=True)

            # TODO: Here we have the inference results.
            
            # Check obstacle distance
            dist = bot.read_rangefinder()
            print(f"Distance ahead: {dist} cm")

            if dist and dist > 40:
                print("Path clear, driving forward...")
                bot.drive_effort(0.5, 0.5)
            else:
                print("Obstacle detected! Turning...")
                bot.drive_effort(0.5, -0.5)

            # Plot bounding boxes and labels onto the frame
            annotated_frame = results[0].plot()

            # Write the variables on the frame.
            var1 = f"Range: {dist}"
            var2 = f"Time: {time.strftime('%H:%M:%S')}"  # Replace with temperature, battery, etc.
            annotated_frame = annotate_frame(annotated_frame, var1, var2)

            # Write the same frame 15 times to hold it on screen for 0.5s
            for _ in range(REPEAT_COUNT):
                out.write(annotated_frame)
                frame_count += 1

            # Calculate remainder of the 0.5s slot to keep exact 2 FPS cadence
            elapsed = time.time() - start_time
            remaining = FRAME_INTERVAL - elapsed
            if remaining > 0:
                time.sleep(remaining)

            # Periodic terminal status update
            if frame_count % 30 == 0:
                print(f"Recorded {frame_count} frames...", end="\r", flush=True)

    finally:
        # Cut off the motors
        bot.drive_stop()
        # Always release resources properly so the video file doesn't corrupt
        cap.release()
        out.release()
        print(f"\nSaved {frame_count} frames to '{output_filename}'.")
