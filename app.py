"""
Hook-to-Short Web Application
Download YouTube audio, extract hooks, and create short videos
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import logging
from pathlib import Path
from datetime import datetime
import subprocess
import threading

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

# Create folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database file for tracks
TRACKS_DB = 'tracks.json'

def load_tracks():
    """Load tracks database"""
    if os.path.exists(TRACKS_DB):
        with open(TRACKS_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_tracks(tracks):
    """Save tracks database"""
    with open(TRACKS_DB, 'w', encoding='utf-8') as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)

def add_track(track_info):
    """Add track to database"""
    tracks = load_tracks()
    track_info['id'] = len(tracks) + 1
    track_info['created_at'] = datetime.now().isoformat()
    track_info['status'] = 'completed'
    tracks.append(track_info)
    save_tracks(tracks)
    return track_info

def download_audio(youtube_url, callback=None):
    """
    Download audio from YouTube
    Returns: dict with track info
    """
    try:
        logger.info(f"⬇️ Downloading from: {youtube_url}")
        
        # Create temp folder for this download
        temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{int(datetime.now().timestamp())}")
        os.makedirs(temp_folder, exist_ok=True)
        
        # Download with yt-dlp
        output_template = os.path.join(temp_folder, '%(title)s.%(ext)s')
        
        cmd = [
            'python', '-m', 'yt_dlp',
            '-f', 'bestaudio',
            '-x',
            '--audio-format', 'mp3',
            '--audio-quality', '192K',
            '-o', output_template,
            '--no-playlist',
            youtube_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"Download error: {result.stderr}")
            return None
        
        # Find downloaded file
        files = os.listdir(temp_folder)
        mp3_files = [f for f in files if f.endswith('.mp3')]
        
        if not mp3_files:
            logger.error("No MP3 file found after download")
            return None
        
        mp3_file = mp3_files[0]
        song_title = mp3_file.replace('.mp3', '')
        
        # Move to main uploads folder
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], mp3_file)
        os.rename(os.path.join(temp_folder, mp3_file), final_path)
        
        # Get file size
        file_size = os.path.getsize(final_path) / (1024 * 1024)  # MB
        
        track_info = {
            'title': song_title,
            'youtube_url': youtube_url,
            'file_path': final_path,
            'filename': mp3_file,
            'file_size_mb': round(file_size, 2),
            'artist': 'Unknown',  # Can be extracted from metadata
            'duration': '0:00'    # Can be extracted from audio
        }
        
        logger.info(f"✓ Downloaded: {song_title} ({file_size:.2f} MB)")
        
        # Add to database
        add_track(track_info)
        
        return track_info
        
    except subprocess.TimeoutExpired:
        logger.error("Download timeout (5 min)")
        return None
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        return None

@app.route('/')
def index():
    """Serve main page"""
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def api_download():
    """API endpoint to download YouTube audio"""
    data = request.json
    youtube_url = data.get('url')
    
    if not youtube_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # Run download in background
    def download_task():
        result = download_audio(youtube_url)
        if result:
            return {'success': True, 'track': result}
        return {'success': False, 'error': 'Download failed'}
    
    # For now, run synchronously
    result = download_audio(youtube_url)
    
    if result:
        return jsonify({'success': True, 'track': result})
    else:
        return jsonify({'success': False, 'error': 'Failed to download audio'}), 500

@app.route('/api/tracks', methods=['GET'])
def api_get_tracks():
    """Get all tracks"""
    tracks = load_tracks()
    return jsonify(tracks)

@app.route('/api/tracks/<int:track_id>', methods=['DELETE'])
def api_delete_track(track_id):
    """Delete a track"""
    tracks = load_tracks()
    tracks = [t for t in tracks if t.get('id') != track_id]
    save_tracks(tracks)
    return jsonify({'success': True})

@app.route('/api/extract-hook', methods=['POST'])
def api_extract_hook():
    """Extract hook from audio"""
    data = request.json
    track_id = data.get('track_id')
    hook_length = data.get('length', 30)
    
    tracks = load_tracks()
    track = next((t for t in tracks if t.get('id') == track_id), None)
    
    if not track:
        return jsonify({'error': 'Track not found'}), 404
    
    try:
        audio_file = track['file_path']
        hook_name = f"{track['filename'].replace('.mp3', '')}_hook.mp3"
        output_file = os.path.join(app.config['OUTPUT_FOLDER'], hook_name)
        
        # Call main.py hook extraction
        cmd = [
            'python', 'main.py',
            audio_file,
            '-o', output_file,
            '-l', str(hook_length)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'hook_file': hook_name,
                'output_path': output_file
            })
        else:
            logger.error(f"Hook extraction error: {result.stderr}")
            return jsonify({'error': 'Hook extraction failed'}), 500
            
    except Exception as e:
        logger.error(f"Error extracting hook: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'tracks': len(load_tracks()),
        'downloads_folder': app.config['UPLOAD_FOLDER'],
        'outputs_folder': app.config['OUTPUT_FOLDER']
    })

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
