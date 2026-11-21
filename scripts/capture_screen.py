"""Capture an isolated X11 display. Optional dependency: mss==10.1.0.

Records real pixels at a constant rate; duplicates the last frame if capture is late.
No screenshots, outputs or metrics are fabricated.
"""
import argparse
import ctypes
import glob
import json
from pathlib import Path
import signal
import subprocess
import time
import mss
import mss.linux

# NixOS keeps X libraries outside the conventional loader search path.
for key, pattern in [('_X11', 'libx11-*/lib/libX11.so.6'),
                     ('_XRANDR', 'libxrandr-*/lib/libXrandr.so.2'),
                     ('_XFIXES', 'libxfixes-*/lib/libXfixes.so.3')]:
    if not getattr(mss.linux, key):
        matches = sorted(glob.glob('/nix/store/*' + pattern))
        for candidate in matches:
            try:
                ctypes.CDLL(candidate)
            except OSError:
                continue
            setattr(mss.linux, key, candidate)
            break

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--display', default=':98')
parser.add_argument('--fps', type=int, default=25)
parser.add_argument('--stop-file', type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
stopping = False

def stop(*_):
    global stopping
    stopping = True

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
with mss.mss(display=args.display, with_cursor=True) as screen:
    bounds = screen.monitors[0]
    size = f'{bounds["width"]}x{bounds["height"]}'
    command = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
               '-f', 'rawvideo', '-pixel_format', 'bgra', '-video_size', size,
               '-framerate', str(args.fps), '-i', 'pipe:0', '-an',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
               '-threads', '4', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(args.output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = 0
    duplicates = 0
    last = None
    start = time.monotonic()
    print('READY', flush=True)
    try:
        while not stopping and not args.stop_file.exists():
            target = start + frames / args.fps
            if target > time.monotonic():
                time.sleep(target - time.monotonic())
            frame = screen.grab(bounds).raw
            due = int((time.monotonic() - start) * args.fps)
            while frames < due and last is not None:
                process.stdin.write(last)
                frames += 1
                duplicates += 1
            process.stdin.write(frame)
            last = frame
            frames += 1
    finally:
        process.stdin.close()
        code = process.wait()
    if code:
        raise SystemExit(code)
    args.output.with_suffix('.capture.json').write_text(json.dumps(dict(
        size=size, fps=args.fps, frames=frames, seconds=frames / args.fps,
        wall_seconds=time.monotonic() - start, duplicated_frames=duplicates,
        method='Actual X11 display pixels captured with MSS and encoded with FFmpeg'), indent=2) + '\n')
