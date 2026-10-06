#!/usr/bin/env python

import serial
import time
from typing import Optional

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200


class XRPController:
    """Client interface for communicating with an XRP robot running usb_control.py."""

    def __init__(self, port: str = SERIAL_PORT, baudrate: int = BAUD_RATE, timeout: float = 3.0):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        self.ser.dtr = True
        self.ser.rts = True
        time.sleep(0.1)
        self.sync_connection()
    
    def sync_connection(self, max_attempts: int = 5) -> bool:
        """Synchronize the serial connection and verify the controller responds."""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        # Send a newline to flush and clear any partial command buffer on the robot
        self.ser.write(b"\n")
        self.ser.flush()
        time.sleep(0.05)
        self.ser.reset_input_buffer()

        # Ping the robot controller to confirm it is responsive
        for _ in range(max_attempts):
            self.ser.write(b"PING\n")
            self.ser.flush()
            time.sleep(0.1)
            while self.ser.in_waiting:
                line = self.ser.readline().decode("utf-8", errors="replace").strip()
                if "ACK:PING" in line:
                    return True
                elif "ACK:" in line or "ERR:" in line:
                    # Received some valid controller response
                    return True
        
        # We were unable to get a ping back.
        return False

    def ping(self) -> bool:
        """Send PING to check controller status."""
        return self.send_command("PING").startswith("ACK:PING")
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying serial connection."""
        if self.ser and self.ser.is_open:
            try:
                self.ser.flush()
                # Deassert DTR and RTS to notify the USB CDC device of disconnect
                self.ser.dtr = False
                self.ser.rts = False
                time.sleep(0.05)
            except Exception:
                pass
            self.ser.close()
    
    def send_command(self, cmd: str, timeout: Optional[float] = None) -> str:
        """Send a command string and return the robot's response."""
        orig_timeout = self.ser.timeout
        if timeout is not None:
            self.ser.timeout = timeout
        try:
            if self.ser.in_waiting:
                self.ser.reset_input_buffer()
            self.ser.write((cmd + "\n").encode("utf-8"))
            self.ser.flush()
            return self.ser.readline().decode("utf-8", errors="replace").strip()
        finally:
            if timeout is not None:
                self.ser.timeout = orig_timeout

    # ---------------------------------------------------------
    # Board / LED
    # ---------------------------------------------------------
    def set_rgb(self, r: int, g: int, b: int) -> str:
        """Set board LED RGB values."""
        return self.send_command(f"RGB,{r},{g},{b}")

    def led_off(self) -> str:
        """Turn off the board LED."""
        return self.send_command("OFF")

    # ---------------------------------------------------------
    # Servos
    # ---------------------------------------------------------
    def set_servo(self, servo_id: int, angle: float) -> str:
        """Set servo (1 or 2) angle in degrees."""
        return self.send_command(f"SERVO,{servo_id},{angle}")

    def free_servo(self, servo_id: int) -> str:
        """Release/free servo (1 or 2)."""
        return self.send_command(f"SERVO,{servo_id},FREE")

    # ---------------------------------------------------------
    # Sensors
    # ---------------------------------------------------------
    def read_rangefinder(self) -> Optional[float]:
        """Query distance from the ultrasonic rangefinder in cm."""
        resp = self.send_command("RF")
        if resp.startswith("ACK:RF,"):
            try:
                return float(resp.split(",")[1])
            except (IndexError, ValueError):
                return 0
                pass
        return None

    # ---------------------------------------------------------
    # Drivetrain
    # ---------------------------------------------------------
    def drive_stop(self) -> str:
        """Stop drivetrain motors."""
        return self.send_command("DRIVE,STOP")

    def drive_effort(self, left: float, right: float) -> str:
        """Set drivetrain motor effort (-1.0 to 1.0)."""
        return self.send_command(f"DRIVE,EFFORT,{left},{right}")

    def drive_speed(self, left: float, right: float) -> str:
        """Set drivetrain speed in cm/s using closed-loop PID."""
        return self.send_command(f"DRIVE,SPEED,{left},{right}")

    def drive_arcade(self, straight: float, turn: float) -> str:
        """Set arcade drive throttle and turn effort (-1.0 to 1.0)."""
        return self.send_command(f"DRIVE,ARCADE,{straight},{turn}")

    def drive_straight(self, distance: float, effort: float = 0.5, timeout: float = 10.0) -> str:
        """Drive straight for a distance in cm."""
        return self.send_command(f"DRIVE,STRAIGHT,{distance},{effort}", timeout=timeout)

    def drive_turn(self, degrees: float, effort: float = 0.5, timeout: float = 10.0) -> str:
        """Turn by specified degrees."""
        return self.send_command(f"DRIVE,TURN,{degrees},{effort}", timeout=timeout)

    # ---------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------
    def stop_program(self) -> str:
        """Send STOP to shut down the robot script gracefully."""
        return self.send_command("STOP")


def main():
    with XRPController() as bot:
        # Example 1: Read rangefinder distance
        distance = bot.read_rangefinder()
        print(f"Initial Rangefinder Distance: {distance} cm")

        # Example 2: Set LED color
        print("Setting LED color...")
        resp = bot.set_rgb(0, 255, 0)
        print("<-", resp)
        time.sleep(1.0)

        # Example 3: Turn left 
        print("Turn left...")
        bot.drive_effort(-0.5, 0.5)
        time.sleep(5.0)
        bot.drive_stop()
        
        # Example 3: Turn right 
        print("Turn right...")
        bot.drive_effort(0.5, -0.5)
        time.sleep(5.0)
        bot.drive_stop()

        # Turn off LED
        bot.led_off()


if __name__ == "__main__":
    main()

