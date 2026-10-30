# oled-measure

Camera-based measurement and calibration for the OLED Tint Decky plugin
(`~/projects/decky-oled-tint`). A Sony camera in PC Remote mode over USB, driven by
gphoto2; grey patches shown full-screen through Steam's UI (debug port 8080).

Everything runs in the `oled-cam` toolbox (gphoto2, rawpy, numpy,
websocket-client):

    toolbox run -c oled-cam python3 measure.py setup
    toolbox run -c oled-cam python3 measure.py measure --steps 4096 --name ref
    toolbox run -c oled-cam python3 measure.py measure --steps 52,96,177,310,543 --name raw
    toolbox run -c oled-cam python3 measure.py report raw --against ref
    toolbox run -c oled-cam python3 measure.py calibrate --steps 177 --reference ref
    toolbox run -c oled-cam python3 measure.py apply runs/proposal-...-177.json

Before long runs, set Steam's screen dimming/sleep to Never.
