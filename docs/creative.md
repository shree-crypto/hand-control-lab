# Air drawing and air instrument

Both experiments stay inside their own camera window and never send Windows mouse/keyboard input. Their camera UI and audio output still need an on-device trial; the automated tests exercise the camera-independent drawing state, note mapping and WAV amplitude bounds.

## Drawing

```powershell
.\.venv\Scripts\python.exe -m gesture_control draw
```

- Move your right index finger, pinch right thumb/index to draw, then release to lift the pen.
- Your left thumb/index separation changes brush radius. Hide your left hand to use `+` / `-` instead.
- `1`–`5` choose colors, `C` clears, `S` explicitly saves paint on a black background to `~/HandControl/drawings/`. Camera frames are not saved.
- Hand loss, camera stalls and implausibly large finger jumps break the stroke, so reacquiring a hand doesn't draw a connecting line across the canvas.

The drawing is a 2D experiment. Camera depth is not used and no physical measurement is implied.

## Air instrument

```powershell
# Silent visualizer first.
.\.venv\Scripts\python.exe -m gesture_control music

# Opt in to local sound on Windows. Start with low speaker volume.
.\.venv\Scripts\python.exe -m gesture_control music --audio
```

Both hands must be visible. Pinch your right thumb/index to play; right-hand height selects one of 25 semitone pitches from 220 to 880 Hz. Left-hand height sets volume. Release the pinch or hide either hand to silence the instrument. Tracking loss passed by the common runtime must invoke an empty-hand frame so sound is stopped.

Sound uses Python's Windows `winsound` module and asynchronously loops a synthesized WAV file. It uses no extra audio package, records no microphone input and sends no MIDI. Temporary WAV files are removed on normal exit. Changes are limited to about eight per second, so this is a playful pitched instrument, not a low-latency professional synthesizer. Non-Windows systems run the visualizer with an explicit no-audio message.

Digital amplitude is capped at 12%; speaker/headphone volume still determines loudness. Sound is opt-in and stops during the handler's normal cleanup. A hard-killed or fully hung process is outside the cleanup guarantee.

Use `--camera 1` if your normal webcam is not camera zero. Escape/Q exits through the common runtime.
