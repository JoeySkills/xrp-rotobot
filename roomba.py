#!/usr/bin/env python

from XRPLib.defaults import Board
from XRPLib.defaults import drivetrain
from XRPLib.defaults import imu
from XRPLib.rangefinder import Rangefinder
from XRPLib.servo import Servo
import time

drivetrain.stop()

# Get a reference to the board
board = Board.get_default_board()
board.led_on()

rf = Rangefinder()

board.led_blink(2)
for i in range(1000):
    distance = rf.distance()
    if (distance > 15):
        drivetrain.set_effort(0.5, 0.5)
    if (distance < 15):
        board.led_on()
        drivetrain.stop()
        drivetrain.set_effort(-.5, .5)
        time.sleep(.5)
        drivetrain.stop()
        board.led_blink(2)
    time.sleep(.05)

drivetrain.stop()
board.led_off()
