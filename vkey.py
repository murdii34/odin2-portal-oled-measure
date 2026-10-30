"""A virtual keyboard over uinput (no extra tools): press keys into the game
in front, for unattended show-off takes.
    vkey.py KEY [KEY ...]     e.g. vkey.py enter enter space esc"""
import fcntl
import os
import struct
import sys
import time

KEYS = {"esc": 1, "enter": 28, "space": 57, "up": 103, "down": 108, "left": 105, "right": 106,
        "z": 44, "x": 45, "c": 46, "e": 18, "f": 33, "j": 36, "k": 37, "tab": 15}
EV_SYN, EV_KEY = 0, 1
UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x5501, 0x5502


def emit(fd, typ, code, val):
    os.write(fd, struct.pack("llHHi", 0, 0, typ, code, val))


def press(names, hold=0.08, gap=0.6):
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        for code in KEYS.values():
            fcntl.ioctl(fd, UI_SET_KEYBIT, code)
        setup = struct.pack("HHHH80sI", 0x03, 0x1234, 0x5678, 1, b"oled-measure keys", 0)
        fcntl.ioctl(fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(fd, UI_DEV_CREATE)
        time.sleep(1.0)                             # let the system pick the device up
        for n in names:
            code = KEYS[n]
            emit(fd, EV_KEY, code, 1); emit(fd, EV_SYN, 0, 0)
            time.sleep(hold)
            emit(fd, EV_KEY, code, 0); emit(fd, EV_SYN, 0, 0)
            time.sleep(gap)
        time.sleep(0.3)
        fcntl.ioctl(fd, UI_DEV_DESTROY)
    finally:
        os.close(fd)


if __name__ == "__main__":
    press(sys.argv[1:])
