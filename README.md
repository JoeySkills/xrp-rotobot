# xrp-rotobot

This is my project to control an [XRP Robot](https://introtoroboticsv2.readthedocs.io/en/latest/index.html) using an NVIDIA [Jetson Orin Nano](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/index.html). This implementation uses a USB connection from the Jetson to the controller board.

## USB Remote Control Architecture

The repository provides a client-server architecture for controlling the XRP robot from a host computer (e.g., PC or SBC) over USB serial:

* **[`usb_control.py`](usb_control.py)**: MicroPython RPC server running on the robot's RP2040 microcontroller. It asynchronously listens on USB serial (`sys.stdin`) for commands and drives the motors, reads the ultrasonic rangefinder/IMU, controls servos, and toggles LEDs.
* **[`usb_controller.py`](usb_controller.py)**: Host-side Python library providing the `XRPController` client class. It manages serial connectivity (`/dev/ttyACM0`), handshakes on connect, flushes stale buffers, and sends commands with automatic response handling.
* **[`look_around.py`](look_around.py)**: Example autonomous application combining computer vision (YOLO) with robot motion control via `XRPController`.
* **[`voice_control.py`](voice_control.py)**: Host-side voice listener that transcribes microphone audio with [Vosk](https://alphacephei.com/vosk/) and streams each utterance to the robot as `TEXT` commands via `XRPController`.

---

### Deploying the Controller to the Robot

1. **Install [`usb_control.py`](usb_control.py) as the robot's boot script:**
   ```bash
   # Copy usb_control.py to the Pico as main.py so it starts automatically
   mpremote cp usb_control.py :main.py

   # Soft-reboot the board to start the service
   mpremote reset
   ```   
2. **Run the [`usb_controller.py`](usb_controller.py) script interactively to test connectivity:**
   ```bash
   # Activate virtual environment
   source .venv/bin/activate
   
   # Launch the vision & navigation script
   python usb_controller.py
   ```

---

### Using `XRPController` in Python Scripts

Import [`XRPController`](usb_controller.py) and use it as a context manager:

```python
from usb_controller import XRPController

# Connects to /dev/ttyACM0 by default and performs a handshake
with XRPController() as bot:
    # 1. Check distance with ultrasonic rangefinder (returns cm as float, or None)
    distance = bot.read_rangefinder()
    print(f"Obstacle distance: {distance} cm")

    # 2. Drive motors (-1.0 to 1.0 effort for left and right wheels)
    bot.drive_effort(0.5, 0.5)

    # 3. Stop drivetrain motors
    bot.drive_stop()

    # 4. Control LEDs or servos
    bot.set_rgb(0, 255, 0)
    bot.set_servo(1, 90.0)
```

---

### Example: Running `look_around.py`

[`look_around.py`](look_around.py) captures video frames from a USB camera, runs YOLO object detection, monitors distance with the rangefinder via `XRPController`, and navigates:

```bash
# Activate virtual environment
source .venv/bin/activate

# Launch the vision & navigation script
python look_around.py
```

* **Behavior**:
  * Reads the front distance sensor via `bot.read_rangefinder()`.
  * If the path is clear (`dist > 40 cm`), it drives forward with `bot.drive_effort(0.5, 0.5)`.
  * If an obstacle is detected, it turns with `bot.drive_effort(0.5, -0.5)`.
  * Annotates and writes output video frames to `annotated_output.mp4`.
* **Stopping**: Press `Ctrl+C` in the terminal. The `finally:` block will automatically call `bot.drive_stop()` to cut power to the motors and release camera and video writer resources cleanly.

---

### Voice Control: `voice_control.py`

[`voice_control.py`](voice_control.py) listens on the host microphone, transcribes speech offline with [Vosk](https://alphacephei.com/vosk/), and sends each recognized utterance to the robot over USB serial. The robot stores the latest transcript in `last_heard` and echoes it back in its response.

**Setup (Jetson Orin Nano / JetPack):**

```bash
# PortAudio backend for sounddevice
sudo apt install -y libportaudio2

# Note: JetPack's root filesystem is read-only. Keep the venv and model on a
# writable partition (e.g., your home directory).
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Download and unzip the small English Vosk model (~40 MB, real-time on the Orin Nano)
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

**Run:**

```bash
# Activate virtual environment
source .venv/bin/activate

# Launch the voice listener
python voice_control.py
```

* **Behavior**:
  * Captures 16 kHz mono audio from the default input device.
  * When Vosk detects the end of an utterance, the transcript is sent as `TEXT,<transcript>`; commas inside the transcript are preserved by the protocol.
  * Each transcript is echoed back as `ACK:TEXT,<transcript>`.
* **Stopping**: Press `Ctrl+C` in the terminal. The `finally:` block calls `bot.drive_stop()` and closes the audio stream.
* **Model**: Set `VOSK_MODEL` to point at a different model directory if needed (e.g., `vosk-model-en-us-0.22` for higher accuracy).

---

### Command Protocol Reference

| Action | Host Python Method | Wire Command | Robot Response |
| :--- | :--- | :--- | :--- |
| **Ping / Handshake** | `bot.ping()` | `PING` | `ACK:PING,PONG` |
| **Rangefinder** | `bot.read_rangefinder()` | `RF` | `ACK:RF,<distance_cm>` |
| **IMU** | `bot.send_command("IMU")` | `IMU` | `ACK:IMU,<pitch>,<heading>,<yaw>` |
| **Speech-to-Text** | `bot.send_command("TEXT,<text>")` | `TEXT,<transcript>` | `ACK:TEXT,<transcript>` |
| **Stop Motors** | `bot.drive_stop()` | `DRIVE,STOP` | `ACK:DRIVE,STOP` |
| **Motor Effort** | `bot.drive_effort(left, right)` | `DRIVE,EFFORT,<l>,<r>` | `ACK:DRIVE,EFFORT` |
| **Speed (PID)** | `bot.drive_speed(left, right)` | `DRIVE,SPEED,<l>,<r>` | `ACK:DRIVE,SPEED` |
| **Arcade Drive** | `bot.drive_arcade(straight, turn)` | `DRIVE,ARCADE,<s>,<t>` | `ACK:DRIVE,ARCADE` |
| **Servo Angle** | `bot.set_servo(id, angle)` | `SERVO,<id>,<deg>` | `ACK:SERVO,<id>,<deg>` |
| **Free Servo** | `bot.free_servo(id)` | `SERVO,<id>,FREE` | `ACK:SERVO,<id>,FREE` |
| **LED Blink** | `bot.set_rgb(r, g, b)` | `RGB,<r>,<g>,<b>` | `ACK:RGB,<r>,<g>,<b>` |
| **LED Off** | `bot.led_off()` | `OFF` | `ACK:OFF` |
| **Terminate Script** | `bot.stop_program()` | `STOP` | `ACK:STOP` *(exits to REPL)* |

> **Note on `STOP` vs. `DRIVE,STOP`**:
> * Always use `bot.drive_stop()` (`DRIVE,STOP`) to halt the robot's wheels.
> * `bot.stop_program()` (`STOP`) terminates [`usb_control.py`](usb_control.py) and exits back to the MicroPython REPL prompt, which requires restarting the script before subsequent runs.
