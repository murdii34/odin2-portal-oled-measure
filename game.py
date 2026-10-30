"""Start or close a Steam game through Steam's own client (CDP), for the
unattended show-off takes.  game.py run APPID | game.py stop APPID"""
import sys
from screen import Screen

s = Screen()
what, app = sys.argv[1], sys.argv[2]
if what == "run":
    print(s.steam.eval(f'SteamClient.Apps.RunGame("{app}", "", -1, 100); true'))
else:
    print(s.steam.eval(f'SteamClient.Apps.TerminateApp("{app}", false); true'))
