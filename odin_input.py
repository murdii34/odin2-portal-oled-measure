"""Press keys on the Odin through a virtual keyboard (uinput), so nobody has
to reach into the hood. A keyboard Enter acts as A in Steam's UI and in games
that take keyboard input (Blasphemous 2: "press any button", then the save slot).

    python3 -I odin_input.py enter enter     # keys: enter, space, esc

Plain python3 on the host (no toolbox): /dev/uinput is open to the user."""
import fcntl, os, struct, sys, time

UI_SET_EVBIT, UI_SET_KEYBIT, UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x40045564, 0x40045565, 0x405c5503, 0x5501, 0x5502
KEYS = {"enter": 28, "space": 57, "esc": 1}

fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(fd, UI_SET_EVBIT, 1)
fcntl.ioctl(fd, UI_SET_EVBIT, 0)
for k in KEYS.values():
    fcntl.ioctl(fd, UI_SET_KEYBIT, k)
fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("HHHH80sI", 3, 0x1234, 0x5678, 1, b"claude-kbd", 0))
fcntl.ioctl(fd, UI_DEV_CREATE)
time.sleep(1.5)                       # let the system see the new device


def ev(t, c, v):
    os.write(fd, struct.pack("llHHi", 0, 0, t, c, v))


for name in sys.argv[1:]:
    ev(1, KEYS[name], 1); ev(0, 0, 0)
    time.sleep(0.1)
    ev(1, KEYS[name], 0); ev(0, 0, 0)
    time.sleep(2.5)
fcntl.ioctl(fd, UI_DEV_DESTROY)
