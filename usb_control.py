#!/usr/bin/env python

import sys
import uselect
import asyncio
import micropython
from XRPLib.defaults import Board, drivetrain, imu
from XRPLib.rangefinder import Rangefinder
from XRPLib.servo import Servo

# Hardware initialization
board = Board.get_default_board()
servo_one = Servo.get_default_servo(1)
servo_two = Servo.get_default_servo(2)
rf = Rangefinder()

# Prevent incoming 0x03 (Ctrl+C) bytes from killing the event loop
micropython.kbd_intr(-1)

# -------------------------------------------------------------
# Command Dispatch Table
# -------------------------------------------------------------
COMMANDS = {}

def command(name):
    """Decorator to register a command handler."""
    def decorator(func):
        COMMANDS[name.upper()] = func
        return func
    return decorator

# Last transcribed text received from the host via the TEXT command
last_heard = ""

@command("STOP")
def cmd_stop():
    """Terminate the program cleanly."""
    return False

@command("RGB")
def cmd_rgb(r, g, b):
    """Control LED RGB values (or blink indicator)."""
    r, g, b = int(r), int(g), int(b)
    board.led_blink(1)
    return f"{r},{g},{b}"

@command("OFF")
def cmd_off():
    """Turn off the board LED."""
    board.led_off()
    return "OK"

@command("SERVO")
def cmd_servo(servo_num, angle):
    """Set servo angle: SERVO,<1|2>,<angle> or free servo: SERVO,<1|2>,FREE"""
    s = servo_one if str(servo_num) == "1" else servo_two if str(servo_num) == "2" else None
    if s is None:
        raise ValueError(f"Invalid servo ID: {servo_num}")
    if str(angle).upper() == "FREE":
        s.free()
        return f"{servo_num},FREE"
    angle_val = float(angle)
    s.set_angle(angle_val)
    return f"{servo_num},{angle_val}"

@command("RF")
def cmd_rangefinder():
    """Query rangefinder distance in cm."""
    dist = rf.distance()
    return f"{dist:.2f}"

@command("IMU")
def cmd_imu():
    """Query the IMU."""
    pitch = imu.get_pitch()
    heading = imu.get_heading()
    yaw = imu.get_yaw()
    return f"{pitch:.2f},{heading:.2f},{yaw:.2f}"

@command("TEXT")
def cmd_text(*parts):
    """Store transcribed host text: TEXT,<transcript> (commas preserved)."""
    global last_heard
    text = ",".join(parts).strip()
    if not text:
        return "OK"
    last_heard = text
    return text

@command("DRIVE")
def cmd_drivetrain(action, *args):
    """Control drivetrain:
    DRIVE,STOP
    DRIVE,EFFORT,<left>,<right>
    DRIVE,SPEED,<left>,<right>
    DRIVE,ARCADE,<straight>,<turn>
    DRIVE,STRAIGHT,<distance>[,<effort>]
    DRIVE,TURN,<degrees>[,<effort>]
    """
    action = action.upper()
    if action == "STOP":
        drivetrain.stop()
    elif action == "EFFORT":
        if len(args) != 2:
            raise ValueError("EFFORT requires <left>,<right>")
        drivetrain.set_effort(float(args[0]), float(args[1]))
    elif action == "SPEED":
        if len(args) != 2:
            raise ValueError("SPEED requires <left>,<right>")
        drivetrain.set_speed(float(args[0]), float(args[1]))
    elif action == "ARCADE":
        if len(args) != 2:
            raise ValueError("ARCADE requires <straight>,<turn>")
        drivetrain.arcade(float(args[0]), float(args[1]))
    elif action == "STRAIGHT":
        if len(args) < 1:
            raise ValueError("STRAIGHT requires <distance>[,<effort>]")
        dist = float(args[0])
        effort = float(args[1]) if len(args) > 1 else 0.5
        drivetrain.straight(dist, max_effort=effort)
    elif action == "TURN":
        if len(args) < 1:
            raise ValueError("TURN requires <degrees>[,<effort>]")
        deg = float(args[0])
        effort = float(args[1]) if len(args) > 1 else 0.5
        drivetrain.turn(deg, max_effort=effort)
    else:
        raise ValueError(f"Unknown drive action: {action}")
    return action

async def handle_command(line: str) -> bool:
    """Dispatches line to registered commands. Returns False if STOP is received."""
    line = line.strip()
    if not line:
        return True

    parts = line.split(",")
    cmd = parts[0].upper()
    args = parts[1:]

    handler = COMMANDS.get(cmd)
    if not handler:
        print(f"ERR:UNKNOWN_CMD:{cmd}")
        return True

    try:
        result = handler(*args)
        if result is False:
            print("ACK:STOP")
            return False

        if result is not None:
            if result == "OK":
                print(f"ACK:{cmd}")
            else:
                print(f"ACK:{cmd},{result}")
        else:
            print(f"ACK:{cmd}")
    except TypeError:
        print(f"ERR:BAD_ARGS:{cmd}")
    except ValueError as e:
        print(f"ERR:INVALID_VAL:{e}")
    except Exception as e:
        print(f"ERR:{cmd}:{e}")

    return True

async def usb_serial_listener():
    """Asynchronously reads incoming lines from USB Serial (stdin)."""
    sreader = asyncio.StreamReader(sys.stdin)
    print("READY")

    while True:
        # Await incoming bytes without blocking other async tasks
        raw_data = await sreader.readline()
        if raw_data:
            line_str = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
            if not await handle_command(line_str):
                break

async def robot_background_task():
    """Example concurrent task (e.g., telemetry heartbeat, sensor polling)."""
    try:
        while True:
            # Simulates non-blocking background logic running every 500ms
            await asyncio.sleep_ms(500)
    except asyncio.CancelledError:
        pass

async def main():
    # Set initial visual ready state (dim blue)
    board.led_on()

    # Run the USB listener and robot tasks concurrently
    bg_task = asyncio.create_task(robot_background_task())
    try:
        await usb_serial_listener()
    finally:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
        drivetrain.stop()
        board.led_off()
        micropython.kbd_intr(3)  # Restore Ctrl+C handling in the REPL

# Start the asyncio event loop
asyncio.run(main())

