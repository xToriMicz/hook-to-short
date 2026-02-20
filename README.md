# Hook-to-Short 🎵➜📱

**Complete workflow**: YouTube URL → Hook Extraction → AI Album Art → Short Video (9:16 vertical)

Extract music hooks, detect mood, generate album art with AI, and create viral short videos - all in one click!

## 🎯 Features

- 🔗 **YouTube Integration** - Paste link, automatically download MP3 (192kbps)
- 🎵 **Smart Hook Detection** - Extract chorus automatically using pychorus
- 🎭 **Mood Detection** - Analyze song title to detect mood (happy, sad, energetic, calm, romantic, angry)
- 🎨 **AI Album Art** - Generate custom images with Kie.ai (Nanobanana Pro model)
  - Thai brush calligraphy typography
  - Mood-aware styling
  - 9:16 vertical format (1K resolution)
- 🎬 **Video Composition** - Combine image + hook into short videos
  - TikTok: 1080×1920, 30fps
  - Instagram Reels: 1080×1920, 30fps
  - YouTube Shorts: 1080×1920, 30fps
- 📊 **Platform-Optimized** - Auto-resize for each platform
- 🦀 **Tauri Desktop App** - Fast, secure, single executable
- 🎨 **React UI** - Beautiful, responsive interface

## 📋 Architecture

```
🖥️ Frontend (React + TypeScript)
    ↓
🦀 Backend (Tauri + Rust)
    ↓
🐍 Python Modules (Core Logic)
    ├─ Mood Detection
    ├─ Hook Extraction
    ├─ AI Image Generation (Kie.ai API)
    └─ Video Composition
```

## Quick Start (Python Desktop UI)

The fastest way to run Hook-to-Short — no Node.js or Rust required:

```bash
pip install -r requirements.txt
python gui.py
```

This launches a CustomTkinter desktop app with three tabs: **Download**, **Library**, and **Create Short**. It calls the Python modules directly (no subprocess bridge needed).

> The Flask web UI (`app.py`) and Tauri desktop app (`src/` + `src-tauri/`) still exist as alternatives.

## 🚀 Installation

### Prerequisites
- Python 3.8+
- FFmpeg (system-level installation required)

### Setup
```bash
# Clone or download project
cd Hook-to-short

# Install dependencies
pip install -r requirements.txt
```

### FFmpeg Installation
- **Windows**: Download from https://ffmpeg.org/download.html or use `choco install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt-get install ffmpeg`

## Usage 📖

### Basic Hook Extraction
```bash
python main.py input.mp3
```
Creates `input_hook.mp3` with the extracted 30-second hook.

### Create Short Video (TikTok)
```bash
python main.py music.mp3 -b background.mp4 -o output.mp4 -p tiktok
```

### Create Short Video (YouTube)
```bash
python main.py music.mp3 -b background.mp4 -o output.mp4 -p youtube
```

### Custom Hook Length
```bash
python main.py input.mp3 -l 20
```
Extracts a 20-second hook instead of default 30 seconds.

### Full Command Options
```bash
python main.py --help
```

Output:
```
usage: main.py [-h] [-o OUTPUT] [-l LENGTH] [-b BACKGROUND] [-p {tiktok,reels,youtube}]
               input

Extract hook from music and create short video.

positional arguments:
  input                 Path to input audio file (mp3, wav, flac, ogg, m4a)

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Path to output audio/video file
  -l LENGTH, --length LENGTH
                        Length of hook in seconds (default: 30)
  -b BACKGROUND, --background BACKGROUND
                        Path to background video file for creating short
  -p {tiktok,reels,youtube}, --platform {tiktok,reels,youtube}
                        Target platform (default: tiktok)
```

## Advanced Usage 🎬

### Add Text Overlay
```python
from effects import add_text_overlay
from moviepy import VideoFileClip

video = VideoFileClip("output.mp4")
video_with_text = add_text_overlay(
    video, 
    text="Check out this song!",
    font_size=56,
    font_color='white',
    position='bottom'
)
video_with_text.write_videofile("output_with_text.mp4")
```

### Add Watermark
```python
from effects import add_watermark

video = VideoFileClip("output.mp4")
video_with_watermark = add_watermark(
    video,
    watermark_path="logo.png",
    position="bottom-right",
    scale=0.2
)
```

### Speed Up Video
```python
from effects import speed_up_video

video = VideoFileClip("output.mp4")
faster_video = speed_up_video(video, speed_factor=1.25)  # 25% faster
```

## Configuration 🔧

Edit `config.py` to customize:
- Platform-specific presets (resolution, fps, bitrate)
- Supported file formats
- Default hook length
- Text overlay styling
- Fade effect durations

## Supported Formats 📁

### Audio
- MP3, WAV, FLAC, OGG, M4A, AAC, WMA

### Video
- MP4, AVI, MKV, MOV, FLV, WMV, WebM

## Project Structure 📂

```
Hook-to-short/
├── main.py              # Main script with hook extraction & video creation
├── video_utils.py       # Video processing utilities
├── effects.py           # Advanced video effects
├── config.py            # Configuration and presets
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Troubleshooting 🔧

### FFmpeg Not Found
```
Error: ffmpeg not found
```
**Solution**: Install FFmpeg and add it to your PATH environment variable.

### "Could not find a clear chorus"
- Try a different song with more prominent chorus repetition
- Adjust the `--length` parameter
- The pychorus library works best with songs that have repeated choruses

### Video File Too Large
- Reduce bitrate in `config.py`
- Use lower resolution preset
- Trim input video beforehand

### Audio-Video Sync Issues
- Try using a different video format
- Ensure background video is not corrupted
- Re-encode video with: `ffmpeg -i input.mp4 -c:v libx264 -c:a aac output.mp4`

## Performance Tips ⚡

1. **Use H.264 codec** - Best compatibility (default)
2. **Lower bitrate for mobile** - TikTok works fine at 5Mbps
3. **Pre-trim videos** - Use shorter background videos
4. **Batch processing** - Process multiple videos in a loop script

## Roadmap 🗺️

- [ ] Batch processing multiple songs
- [ ] YouTube auto-upload integration
- [ ] Web UI dashboard
- [ ] Beat detection for clip timing
- [ ] Background music library integration
- [ ] ML-powered scene detection

## Contributing 🤝

Improvements and features welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## License 📜

MIT License - Use freely

## Disclaimer ⚖️

Ensure you have proper licensing/rights for:
- Input music files (for commercial use)
- Background video content
- Downloaded tracks

Always respect copyright and music licensing agreements.

---

**Made with ❤️ for content creators**
