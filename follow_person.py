import signal
import sys
import cv2
import time
from ultralytics import YOLO
from usb_controller import XRPController

DEBUG = False
FRAMES_PER_LOOP = 3 # Set this to slow down the video.
OUTPUT_VIDEO = True # Don't create a video to speed things up
DRIVE_EFFORT = .8
FUDGE = .2
STOP_DISTANCE = 40
FOLLOW = True # Set this to false if you just want to pivot

# Flag to handle clean shutdown on Ctrl+C
running = True

def signal_handler(sig, frame):
    global running
    print("\nStopping capture and saving video...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

# Load model (e.g., yolo11n.pt or yolov8n.pt)
model = YOLO("yolo26n.pt")

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

# Filename for the output video
output_filename = "annotated_output.mp4"
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

# Text box properties
box_width = 320
box_height = 80
margin = 15

last_offset_x = .5 # Set to pivot right by default

print(f"Recording from camera {camera_index} ({width}x{height} @ {fps:.1f} FPS)...")
print("Press Ctrl+C in terminal to stop recording.")

frame_count = 0

def annotate_frame(frame, var1, var2):
    overlay = frame.copy()
    
    # Box top-left: (x1, y1), bottom-right: (x2, y2)
    x1 = margin
    y1 = height - margin - box_height
    x2 = margin + box_width
    y2 = height - margin

    # Text baselines positioned inside the badge
    line1_pos = (x1 + 10, y1 + 30)
    line2_pos = (x1 + 10, y1 + 65)
    
    # Text appearance settings
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    text_color = (0, 255, 0)       # Green (BGR)
    thickness = 2

    # Draw a dark background rectangle in the bottom-left for readability
    cv2.rectangle(overlay, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 0), -1)
    # Draw Variable 1
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
    
    # Blend the frame and the overlay
    output = cv2.addWeighted(frame, 0.5, overlay, 0.5, 0)
    return output

def find_primary_person(results, model):
    """
    Finds person detections and returns the primary target (largest bounding box).
    Returns (target_box, (x1, y1, x2, y2), conf, offset_x) or None if no person found.
    """
    if not results or len(results) == 0 or results[0].boxes is None:
        return None

    boxes = results[0].boxes
    best_target = None
    max_area = 0.0

    for i in range(len(boxes)):
        cls_id = int(boxes.cls[i].item())
        cls_name = model.names.get(cls_id, "")

        if cls_name == "person" or cls_id == 0:
            coords = boxes.xyxy[i].tolist()
            x1, y1, x2, y2 = coords
            conf = float(boxes.conf[i].item())
            area = (x2 - x1) * (y2 - y1)

            if area > max_area:
                max_area = area
                best_target = ((x1, y1, x2, y2), conf)

    return best_target


with XRPController() as bot:
    try:
        while running and cap.isOpened():
            # MAIN LOOP
            loop_start_time = time.time()

            # Read a frame from the camera
            success, frame = cap.read()
            if not success:
                print("Warning: Dropped frame or camera disconnected.")
                break
            
            # Run inference
            results = model(frame, conf=0.5, verbose=DEBUG)
            inference_time = time.time() - loop_start_time

                
            # Here we have the inference results. Find the biggest person.
            person_info = find_primary_person(results, model)
            
            # Check obstacle distance
            dist = bot.read_rangefinder()
            rf_read_time = time.time() - loop_start_time - inference_time

            left_effort = 0
            right_effort = 0
            offset_x = 0
            # If there's a person, we're following.
            if person_info is not None:
                if dist is not None and 0 < dist <= STOP_DISTANCE:
                    bot.drive_stop()
                else:
                    frame_center_x = width / 2.0
                    (x1, y1, x2, y2), conf = person_info
                    person_cx = (x1 + x2) / 2.0
                    offset_x = round((person_cx - frame_center_x) / frame_center_x, 3)  # Range: -1.0 to +1.0
                    # This sets up a pivot
                    left_effort = DRIVE_EFFORT * offset_x
                    right_effort = DRIVE_EFFORT * (offset_x * -1)
                    
                    # Right now we're pivoting.
                    # If we want to follow, we have to get rid of the negative efforts
                    if FOLLOW:
                        if offset_x < -FUDGE:
                            # Target is on the left - slow the left motor
                            left_effort = DRIVE_EFFORT * abs(offset_x ** .5)
                            right_effort = DRIVE_EFFORT
                        elif -FUDGE <= offset_x <= FUDGE:
                            # Target is in the middle - full speed
                            left_effort = DRIVE_EFFORT
                            right_effort = DRIVE_EFFORT
                        elif offset_x > FUDGE:
                            # Target is on the right - slow the right motor
                            left_effort = DRIVE_EFFORT
                            right_effort = DRIVE_EFFORT * abs(offset_x ** .5)

                # Round out the numbers
                left_effort = round(left_effort, 3)
                right_effort = round(right_effort, 3)
                last_offset_x = offset_x
            
            else: # No person
                # Pivot slowly and wait for someone to enter the frame.
                GOVERNOR = .7
                if last_offset_x <= 0:
                    left_effort = -DRIVE_EFFORT * GOVERNOR
                    right_effort = DRIVE_EFFORT * GOVERNOR
                elif last_offset_x > 0:
                    left_effort = DRIVE_EFFORT * GOVERNOR
                    right_effort = -DRIVE_EFFORT * GOVERNOR
            
            # Adjust motor effort
            bot.drive_effort(left_effort, right_effort)

            # Plot bounding boxes and labels onto the frame
            if OUTPUT_VIDEO:
                annotated_frame = results[0].plot()
                # Write the variables on the frame.
                var1 = f"Range: {dist}"
                var2 = f"O:{offset_x} L:{left_effort} R:{right_effort}"
                annotated_frame = annotate_frame(annotated_frame, var1, var2)

                # Save the frame to the output video
                for f in range(FRAMES_PER_LOOP):
                    out.write(annotated_frame)
                    frame_count += 1
            video_write_time = time.time() - loop_start_time - inference_time - rf_read_time 
            

            # Debug output
            loop_time = time.time() - loop_start_time
            if DEBUG:
                print(f"Frame {frame_count}, Dist {dist}, Time {loop_time:f}, ITime {inference_time:f}, RTime {rf_read_time:f}, WTime {video_write_time:f}")

    finally:
        # Cut off the motors
        bot.drive_stop()
        # Always release resources properly so the video file doesn't corrupt
        cap.release()
        out.release()
        print(f"\nSaved {frame_count} frames to '{output_filename}'.")
