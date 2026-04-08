# mp4_player

A simple MP4 player that sequentially plays all MP4 files in the current directory.

## Overview

`mp4_player` is a lightweight video player built with Python (OpenCV + tkinter). It scans the current directory for `.mp4` files and plays them sequentially with a dark-themed GUI.

## Features

- Sequentially plays all MP4 files in the current directory
- Dark-themed GUI with video display
- Play / Pause / Stop controls
- Next / Previous video navigation
- Seek bar for jumping to any position
- File list panel with click-to-play
- Auto-advances to the next video when playback finishes
- Keyboard shortcuts

## Installation

### Using pip

```bash
git clone https://github.com/furuya02/mp4_player.git
cd mp4_player
pip install -e .
```

After installing, the `mp4_player` command will be available:

```bash
mp4_player
```

## Usage

Navigate to a directory containing MP4 files and run:

```bash
cd /path/to/your/videos
mp4_player
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `→` | Next video |
| `←` | Previous video |
| `Esc` | Quit |

### Controls

| Button | Action |
|--------|--------|
| ⏮ 前へ | Previous video |
| ▶ 再生 / ⏸ 一時停止 | Play / Pause |
| ⏹ 停止 | Stop (return to beginning) |
| ⏭ 次へ | Next video |

## Requirements

- Python 3.10 or higher
- tkinter (usually included with Python)

Dependencies installed automatically:
- opencv-python >= 4.8.0
- Pillow >= 10.0.0

> **Note:** This player displays video only (no audio playback). Audio support may be added in a future release.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
