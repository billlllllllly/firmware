# Light Dance Firmware

Controller-side scripts for running the Light Dance show: broadcasts time
pulses to the Pico W dancers over UDP, plays the music track in sync, and
previews each dancer's lights in a Qt window.

## Files

- `control3.py` — main controller + UI entry point.
- `fetch_lightdata.py` — downloads the show data and caches it to `lightdata.npz`.
- `ui.py` — Qt window / dancer-figure widgets.
- `2026_show.mp3` — bundled music track.
- `main.cpp`, `platformio.ini` — Pico W firmware.

## How to use

Follow these steps in order. Steps 1 and 2 need internet; step 3 onward
runs on the internal broadcast LAN.

### 1. Fetch light data (needs internet)

`lightdata.npz` is the per-player frame timeline. Download it once while
you still have internet — `control3.py` will then load from this cache,
no internet required at show time.

```
python fetch_lightdata.py                     # default user "eesa3", LATEST
python fetch_lightdata.py <user>              # custom user, LATEST
python fetch_lightdata.py <user> <time>       # custom user + timestamp
```

The `.npz` is written next to the script and picked up automatically.
Re-run this whenever the show data changes.

### 2. Download the music and update the path (needs internet)

Grab the music track for the show and save it locally. Then open
`control3.py` and edit the hard-coded path at the top:

```python
MUSIC_FILE = r"C:\School_2025\LightDance\picow-pio-template\test music\2026_show.mp3"
```

Point it at wherever you saved the file, e.g.:

```python
MUSIC_FILE = r"C:\School_2025\LightDance\Firmware\firmware\2026_show.mp3"
```

`MUSIC_OFFSET` (just below) shifts the music vs. the broadcast clock in
seconds — positive = music ahead, negative = music behind.

### 3. Switch to the internal broadcast network

Connect your computer to the internal LAN that the Pico W dancers are
on. The controller auto-detects your IP and derives the broadcast
address (`x.y.z.255`) from it, so you must be on the same subnet as the
dancers — otherwise the heartbeats and time pulses will not reach them.

### 4. Run the controller

```
python control3.py
```

This opens the dancer-grid window, discovers Pico W dancers on the LAN
via UDP heartbeats, and on **Start** plays the music and broadcasts the
time clock so every dancer stays in sync. Type a start offset in
seconds in the input box if you want to begin partway through the show.
