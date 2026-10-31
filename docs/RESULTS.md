# Results

Measured with a Sony A7 III + Sigma 35mm f/1.4 at f/2.8, defocused, in a
printed light hood; raw ratios, black frame subtracted. "Light" is relative to
the panel's own curve at full brightness, anchored at grey 64 (1.00x = right);
colour is the red/green and blue/green ratio against the same reference.

## The problem, at backlight 177 (the worst point), correction off

| Grey | Light | R/G | B/G |
|---|---|---|---|
| 4 | 21.76x | -49% | -41% |
| 8 | 8.71x | -36% | -30% |
| 12 | 4.38x | -15% | -12% |
| 16 | 2.87x | -0% | +0% |
| 24 | 1.88x | +2% | -1% |
| 32 | 1.59x | -0% | -1% |
| 48 | 1.16x | -1% | -0% |

Cause: each subpixel jumps from code 1 (almost off) to a far too bright code 2.
Code 2 gives 28% of code 32's light for green, 12% for blue, 9% for red (a 2.2
gamma would give 0.2%). Green's pedestal being highest is the green cast.

## With the correction (night run, 2026-10-24 09:00, static dither, centre)

| Grey | Light | R/G | B/G |
|---|---|---|---|
| 4 | 0.95x | +2% | +0% |
| 8 | 1.00x | +0% | -1% |
| 12 | 0.99x | +0% | -1% |
| 16 | 0.93x | +1% | +1% |
| 24 | 0.98x | -2% | -2% |
| 32 | 0.95x | -0% | -1% |
| 48 | 1.01x | +0% | +0% |

Steps 96 and 310 alike (light 0.98-1.04x, colour within +-3%). Recalibrated
2026-10-24 with the final dither (blue noise in 1x4 cells, pair mode in games,
still in Steam's UI, gamma 2.2 target): colour within about +-3% from grey 8 to
48 at 96, 177 and 310; grey 4 remains the weak spot (10-16% in light).

The full spec sheet with charts: `measure/report/index.html` (also served on
the local network by the Odin).

## What the panel does (findings, in order of discovery)

1. **Pedestal per subpixel** at backlight ~52-543, worst at 177 (above).
2. **Fine patterns blur from row to row, not along a row.** A 1-pixel
   checkerboard gives 30-41% of solid light instead of 50%; columns are
   honest, rows lose up to 40%. Hence dither cells 1 pixel wide, 4 rows tall.
3. **Steam's colour vibrance mixes channels.** At 0.5 (default) gamescope's
   gamut mapping sends a red-only code 16 with 3x the green; at 1.0 channels
   are pure. Not a 3x3 matrix: greys untouched, dark saturated colours
   treated differently. The plugin holds 1.0 while dithering.
4. **Uneven at low drive, two-dimensional.** With dithering, grey 4 ranges
   0.4-2.4x across the screen (bottom-left brightest); grey 48 within +-5%.
   Confirmed panel-side by turning the camera 180 degrees.
5. **Pixels switched every frame lose ~40% of their light** at backlight 177
   (a full-frame flash gives 0.30 instead of 0.50). The moving dither switches
   between neighbouring levels and loses far less; golden-ratio mode loses a
   lot at grey 4, pair mode doesn't.
6. **Tone curve.** At full brightness: gamma 2.2 within +-3% from grey 32 to
   255, lifted below (grey 8 1.46x, grey 4 2.1x over 2.2). At 543 similar,
   grey 8-48 1.12-1.49x.
7. **At full brightness the panel is reference class:** grey tracking within
   +-1% from grey 32 up, uniformity +-6-7% (including lens vignetting), true
   black.

## Hardware notes

- Display controller: Chipone ICNA3512 (Linux driver panel-chipone-icna35xx);
  backlight 40-4096 raw.
- gamescope 3.16.31-ogc1+, HDR output on, SDR content at 202.6 nits; has a
  built-in mura correction (`--mura-map`), a candidate engine for a 2D map.

8. **The bad band has sharp edges** (backlight sweep, 2026-10-24): grey 32
   jumps from neutral to green between backlight 60 and 69 and is neutral
   again from about 530; worst at 100-120 (2.4x too bright, R/G -31%). The
   panel switches drive mode there; a shallow ~1.3 kHz ripple (1-3%) appears
   only inside the band. Below 64 the panel is clean but barely dims (white
   1.1-1.4% of full).
9. **Software dimming at 543 doesn't beat the correction:** the panel's low
   end at 543 isn't clean either (grey 4 green, grey 12-16 purple), and
   gamescope's SDR gain is applied after the shader, so it can't combine with
   an exact dither.
10. **Stray light in the rig is under 0.5%** (reddish); bright content next
    to dark greys shifts them by at most 2.6%.
11. **Readings repeat within ±1-3%** near black (8 shots each of grey 4 and 8
    at 177, still and pair dither, 2026-10-25): the remaining errors are
    systematic, not noise.
12. **Accuracy sweeps** (grey 4-32 at 13 backlight steps, light against gamma
    2.2 from grey 128, colour against the same grey at full brightness):
    inside the band (70-450) the corrected median colour error went 6.2% ->
    4.2% and the light error 26% -> 24% when the dither tables were blended
    between calibrated steps in log brightness (sweep 1 -> 2).
13. **The dithered darks sat 1.2-1.35x too bright**, uniformly, because the
    dither aims at grey 64's light, which is ~20% high against grey 128 at
    these backlights. A lift at grey 64/80/96 per step (closed loop) brought
    grey 16-32 to 1.00-1.09x, but turned grey 4-8 red/magenta (up to +167%
    R/G at 177): the trims were tuned for the old targets and the panel
    doesn't respond in proportion near black (sparse green pixels lose more).
    Fix: re-run the trims with the lift in place.
14. **The band's bottom edge is a lottery:** 56-62 always clean, 70+ always
    in the bad mode, 64-68 either, picked fresh each time, not by direction
    (band_edge.py, 36 points). The plugin steps the backlight over 63-69.
15. **The hood is light-tight:** black frames at 15 s ISO 6400 show no
    difference between a dark room, a lit one and a lamp aimed at the hood
    (all within the frame-to-frame scatter, under 0.1% of the weakest signal
    measured).
16. **The Odin never moved in the hood** (edge positions stable to under a
    pixel within sessions); one framing/focus jump on 24 Oct between 17:07
    and 19:57 (~32 px, edges 2.5x softer), most likely the focus-by-wire lens
    refocusing after a camera power cycle. Centre readings unaffected.
17. **With a Steam menu open over a game, GAMESCOPE_FOCUSED_APP turns to
    Steam's UI (769) while GAMESCOPE_FOCUSED_APP_GFX stays the game**; the
    latter is what ReShade's effect follows and tells a menu over a game from
    Steam's own UI without guessing.
18. **Tables of their own between the old steps fix the blend at grey 4-8**
    (night 2026-10-25/26: tables at 85, 150, 230, 380 + loops): grey 8's
    colour error is now mostly <=10% across the band (230 and 380: 2%), grey
    4 10-30% (its floor: a handful of lit pixels). In the band 42% of the
    points within +-3% colour and +-10% light (36% the day before).
19. **The band's bottom edge wanders:** with the snap certainly off, 56 was
    clean, 58-60 either and 62 already in the bad mode (grey 4 19x), where
    the day before 62 was clean and 64-68 either. The snap now covers
    57-69 (to 56 or 70).
20. **The camera reads ~12-24% more light after the A7 IV session** (focus
    changed): uniform, colour ratios identical; all calibration is ratios
    within a session, so unaffected. Absolute values hold only within one
    focus setting.
21. **The A7 IV matches the A7 III** (2026-10-26, step 4096, 16 greys): R/G
    within 2%, B/G within 1%, relative light within 1-2% from grey 12 to
    192 (grey 255 7% lower, the shortest exposures). Linear in shutter and
    ISO within ~1%; read noise ~2.5 counts (of ~15900) at ISO 800; 15 s
    exposures work. It is far more sensitive: the full-brightness reference
    needs 2 ms exposures.
22. **Why the slider jumped:** Steam's D-pad repeats every ~50 ms and our
    "hold back the first request after a pause" rule held every one of them
    (target stuck at the floor, then a jump at the end); and the gain ladder
    moved in 7% light steps. Both fixed (2% steps, stream window 120 ms).

23. **Floor dimming accuracy, first full sweep** (2026-10-26, A7 IV, profile "Camera",
    24 targets 57-542 x 16 greys, `runs/floor-sweep-a7iv.json`): greys 64 and 128
    colour within 1-2% at every target, light within +-2% down to target ~100
    (up to 1.10x at 57). Grey 32 colour 2-11%, light up to 1.23x at the low end.
    Grey 16 colour 7-28%, grey 8 colour 9-26% and light only 0.75-0.80x from
    target ~366 up to the floor itself (the undimmed floor at 543 already has
    grey 8 at 0.80x, 16.5% colour). So: the darks at the floor (543 curve) are
    the calibration job of the night queue; the lowest targets (57-100: grey 16
    25-28% colour) probably need a correction per target, since the shader
    dims those greys down onto the panel's lowest codes.
24. **The handover at the band's bottom, in numbers** (2026-10-27, `runs/handover-a7iv.json`,
    profile "Camera"): crossing from the panel's own backlight 56 to floor-dimmed
    target 57, white (grey 255) steps +5.9% and grey 128 +7%, but grey 32 +19%
    (126 -> 150): below the handover the panel's dark greys stay flat at ~127 from
    backlight 40 to 56 (they don't follow the backlight), while floor-dimmed dark
    greys follow the white curve. Above, 57 -> 100 rises smoothly (white x2.3).
    So the visible jump is mostly in the darks. Candidates: a lower handover,
    a brightness trim on the lowest ladder steps, or lifting the real-backlight
    darks.
25. **Flicker at the floor, first look** (2026-10-27, `runs/pwm-20261027-002129.json`, 250 us and
    1000 us exposures, row ripple of a grey patch): ripple 0.7-2.6% of the mean at
    backlight 96-310, 3-4% at 52 and 3.5-4.3% at 543, 1217 and 4096. A few percent
    everywhere, the floor (543) not worse than full brightness; no clear PWM
    signature to separate. Treat as "no flicker problem found", not as a proof
    (the camera's shutter reads out row by row; a single patch).
26. **Repeatability:** the floor sweep repeated on an unchanged profile (night 2026-10-26/27,
    `floor-sweep-a7iv` vs `-cal`) moved the mean colour error from 9.0% to 9.6% and the
    mean light error from 8.0% to 8.6% (greys <= 96): about half a point of
    noise or drift between two runs two hours apart. Differences below ~1 point aren't
    real; the profile decision now asks for more than that.
27. **Banding under flat gain, and the floor-anchored fix** (2026-10-28; plugin `main.py`
    + `tests/test_floor.py`; mechanism, camera confirmation still to come): floor dimming
    used to scale the whole colour lookup by the gain G (G<1). Codes below the panel's grey
    floor (the dither table's hand-over code V, the bottom of the banded range) get pulled
    below the panel's lowest visible level, so the sub-floor range collapses into a few
    codes and bands. The fix anchors the gain at the floor: `min(L, Floor) + max(L - Floor,
    0) * G` leaves sub-floor codes untouched and only pulls the codes above the floor toward
    it; with Floor 0 (no table, outside the band) it is exactly the old flat gain. 8 unit
    tests pin it down (sub-floor passthrough, floor point fixed, monotone, G<1 darkens only,
    G=1 identity, Floor=0 equals flat gain, and the w=0 effect equals the no-table effect
    apart from Floor); full suite 129 tests, 0 failures.
    **Correction (review 2026-10-30):** as committed the anchor never ran in floor dimming:
    it took the table from the current backlight, which is held at 543, above the band, so
    Floor was 0 (every compiled effect had `Floor = 0.000000`). `floor-sweep-postanchor`
    therefore measured the old flat gain; its difference from `floor-sweep-a7iv` is the
    profile (Camera -> Camera IV), not the anchor. It must not run either: every table's
    hand-over code is 64, so with the anchor nothing below grey 64 dims (at target 57 the
    darks 9x, white 2.2x too bright). Floor dimming keeps the flat gain; the banding it was
    meant to fix was never measured.
28. **Grey 4-8 went green between two nights, same profile and shader** (`floor-sweep-a7iv-cal2`
    10-27 vs `floor-sweep-postanchor` 10-29, both "Camera IV", both flat gain): at 543
    undimmed grey 4 R/G 0.401 -> 0.203 at equal light, grey 8 0.375 -> 0.289, grey 16 15%
    brighter. Not code. Suspects: Steam's colour vibrance (0.5 mixes channels at dark codes,
    finding 3; held at 1.0 only while dithering, the sweeps run undithered), drift of the
    rig. Next sweep logs the vibrance.
    **Narrowed 2026-10-30 (from the 12x5 grids, no new shots):** not vibrance (it leaves greys
    alone, finding 3; it reads 1.0, SDR content 202.6 nits as documented). Grey 64 and white
    were a uniform 17-18% brighter on 10-29 at the same shutter and ISO, colour unchanged
    (ratio 1.00 in every cell); the outer row and the right column moved less (1.0-1.1),
    which looks like a slightly different framing. Grey 4 lost about half its red in every cell.
    A light change that leaves colour alone points at the rig (aperture, position: the Odin
    was out of the hood on 10-27). Darks changing colour point at the panel: 543 sits only 13
    above the band's upper edge (530), and that edge is known to wander, so the panel may have
    been in its in-band drive mode on 10-29. Both can hold at once. To settle it next session:
    shoot the a7iv-ref reference first (rig check), then grey 4-32 at 543 and at ~600. Sweeps
    now store `conditions` (vibrance, SDR nits, switches, sysfs backlight) at start and end.
29. **Floor dimming dims evenly; the panel's lowest codes don't** (2026-10-30, from the 12x5
    grids of `-cal2` and `-postanchor`, no new shots): per cell, dimmed light over the same cell
    undimmed. Grey 64 and white keep within 0.2-2.5% (standard deviation) at every target down to
    57, colour within 0.1-2%. Grey 16 spreads with the dimming: 1% at target 404, 7% at 204,
    17% at 103 and 49% at 57 (a good night; 126% on 10-29). Grey 16 at target 57 lands on about
    code 6, where the panel itself is patchy (finding 4: grey 4 ranges 0.4-2.4x across the
    screen). So the unevenness is the panel's low end, not the method; a 2D correction would only
    matter for content dimmed into the lowest ~8 codes.
30. **The 10-29 puzzle, measured 2026-10-30** (`rig-check-20261030`, `session-floor543`,
    `session-floor600`; vibrance 1.0 logged): (a) at full brightness the camera now reads
    16-18% more light than the 10-26 reference with identical colour (within 0.7%): the
    +17% of 10-29 was the rig (aperture/focus after a move), not the panel. (b) The darkest
    greys at the floor drift from day to day with the same profile and shader: grey 4 R/G
    against the reference +5% (10-27), -47% (10-29), -18% (10-30); grey 16 stays within
    -5..-1%. (c) A floor of 600 doesn't help: grey 4 -33%, grey 8 -21% there, greener than
    543 today; but the profile is calibrated at 543 and only blended toward 4096 at 600, so
    this doesn't settle the band-edge idea. Floor dimming at 543 today: median colour 3.3%,
    light 4.1%, grey 4-8 colour 37%. Next: what moves the panel's lowest codes from day to
    day (temperature, time since boot), and whether a correction for grey 4-12 at the floor
    can follow it. The 600 sweep stopped after its undimmed shots (handshake bug, fixed).

31. **The darks' drift is temperature** (2026-10-30, `drift-20261030-r01..14`, log
    `drift-20261030-log.jsonl`, `drift_summary.py`): raw panel at 543 (correction off), greys
    4-16 every 12 min for 2.6 h through warm (game running) / cool (game closed) / hot (CPU
    load) / cool. Grey 4 R/G 0.58-0.61 warm (CPU 63-68 C), down to 0.42 after 50 min cool (CPU
    42 C), back up to 0.56 under load, down to 0.47 again: reversible, so not time or wear.
    Grey 4's light moves with it (~25% darker cool), grey 8 R/G 0.476 -> 0.439 (-8%), grey 12
    -3%, grey 16 -1.5%. Correlation of R/G with the CPU temperature 0.73-0.84, the battery
    0.72-0.78, uptime negative (only the cooling in disguise). The panel follows within ~15-30
    min, faster than the battery sensor after the load stopped (rounds 13-14: battery 35-34 C,
    grey 4 already 0.52 -> 0.47), so a smoothed SoC temperature is the better proxy. Explains
    RESULTS 30's day-to-day spread (+5% / -47% / -18%): how warm the Odin was. Cooler = greener
    and darker at the lowest codes. Next: a correction for grey 4-12 at the floor that follows
    temperature; needs a cold point (from standby) and a long-game hot point to fit.
32. **The hand-over flashes and blacks out** (2026-10-30, `stairs-video-t1`, A7 IV USB streaming
    30 fps, grey 128, slider 0->25->0% via Steam's SetBrightness at 1 / 0.5 / 0.25 s per 1% step,
    `stairs_video.py`): every pass **up from 4% to 5%** (native 53 -> floor dimming at 543) shows
    the patch at ~4.6x its level (148 vs 32-35, i.e. undimmed 543) for 4 frames (~130 ms) at 1 s
    per step, and for 15-32 frames (0.5-1.1 s) at 0.5 and 0.25 s per step: the backlight reaches
    543 before the dimming does, and quick steps keep the dimming from catching up. Every pass
    **down from 5% to 4%** blacks out for 2-4 frames (to ~15% of the level: the backlight at 53
    while the dimming gain still applies). No other step jumps (+-10% at most). murdii saw it by
    eye ("BAM"). Settled values (`stairs-20261030`, stills, 1.5 cycles): the hand-over also
    settles uneven (white +9.5%, grey 16 -18%, darks red -> green), up/down differ by the panel.
33. **Hand-over fixed to a short dip** (2026-10-30, `handover-s1..s3`, `handover_sweep.py`, plugin
    711a5fd and after): the floor's ladder effect now stays on screen below the band on a
    pass-through technique, so the 4% <-> 5% crossing is a technique switch, no compile. Filmed
    lead sweep: the technique switch shows fast, the backlight lands a bit later, and the two
    jitter by 1-2 frames between crossings (lead 0: ~1.5 frames off, flash or dip at random;
    lead >= 80 ms up: pure dip growing with the lead; technique-first down: pure flash). So the
    order is chosen to leave only dips: up = dimming 80 ms ahead of the backlight, down =
    backlight 60 ms ahead of the pass-through. `handover-s3` (10 up, 10 down): no flash (worst
    1.04x = noise), dips to ~14% for ~3 frames up, ~4.5 frames down; before (t1) 4.6x for 4
    frames at 1 s steps and up to 32 frames when stepping fast. A smooth hand-over would need
    a ramp across the band (several matched backlight/gain steps in ~100 ms): next idea.
9. **Second unit confirmed** (2026-10-31, field report, no camera): a friend's
   Odin 2 Portal with floor dimming installed via Decky "install from URL":
   "no more green". So the bad band is not one panel's quirk, and the fix
   carries over without per-unit calibration (eye check only).
