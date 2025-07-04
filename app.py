from flask import Flask, request, jsonify
from res480Downloader import download480
from upload import upload_blob
import os
import time
import subprocess
import threading
from titleGetter import getTitle

app = Flask(__name__)
download_proc = None
uploader_thread = None
uploaded_chunks = set()
stop_event = threading.Event()

# Globals for chunked download/upload
chunked_download_proc = None
chunked_uploader_thread = None
uploaded_chunks = set()
chunked_stop_event = threading.Event()

# Status tracking
download_status = {
    'active_downloads': {},
    'total_downloads': 0,
    'total_chunks_uploaded': 0,
    'system_status': 'idle'
}

# Set your bucket name here or use an environment variable
BUCKET_NAME = "hidden-matter-450501-n0_cloudbuild"

@app.route('/diagnose', methods=['GET'])
def diagnose():
    """Diagnostic endpoint to check system status"""
    try:
        # Check yt-dlp version
        yt_dlp_result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True
        )
        yt_dlp_version = yt_dlp_result.stdout.strip() if yt_dlp_result.returncode == 0 else "Not available"
        
        # Check if cookies file exists
        cookies_exist = os.path.exists("cookies.txt")
        
        # Check ffmpeg
        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True
        )
        ffmpeg_available = ffmpeg_result.returncode == 0
        
        return jsonify({
            'yt_dlp_version': yt_dlp_version,
            'cookies_file_exists': cookies_exist,
            'ffmpeg_available': ffmpeg_available,
            'system_status': 'OK' if yt_dlp_version != "Not available" and ffmpeg_available else 'Issues detected'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """Get current download and upload status"""
    global download_status, chunked_download_proc, chunked_uploader_thread
    
    try:
        # Update active downloads status
        active_downloads = {}
        for dir_name in os.listdir('.'):
            if os.path.isdir(dir_name) and not dir_name.startswith('.'):
                chunk_files = [f for f in os.listdir(dir_name) if f.startswith('chunk_') and f.endswith('.mp4')]
                uploaded_count = len([f for f in chunk_files if f in uploaded_chunks])
                total_chunks = len(chunk_files)
                
                # Check if download process is still running
                is_downloading = False
                if chunked_download_proc:
                    is_downloading = chunked_download_proc.poll() is None
                
                active_downloads[dir_name] = {
                    'total_chunks': total_chunks,
                    'uploaded_chunks': uploaded_count,
                    'remaining_chunks': total_chunks - uploaded_count,
                    'is_downloading': is_downloading,
                    'is_uploading': chunked_uploader_thread and chunked_uploader_thread.is_alive(),
                    'progress_percentage': round((uploaded_count / max(total_chunks, 1)) * 100, 2)
                }
        
        # Calculate totals
        total_active = len(active_downloads)
        total_chunks_uploaded = sum(d['uploaded_chunks'] for d in active_downloads.values())
        
        # Determine system status
        if total_active > 0:
            if any(d['is_downloading'] for d in active_downloads.values()):
                system_status = 'downloading'
            elif any(d['is_uploading'] for d in active_downloads.values()):
                system_status = 'uploading'
            else:
                system_status = 'processing'
        else:
            system_status = 'idle'
        
        return jsonify({
            'system_status': system_status,
            'active_downloads': total_active,
            'downloads': active_downloads,
            'total_chunks_uploaded': total_chunks_uploaded,
            'total_downloads_completed': download_status['total_downloads'],
            'timestamp': time.time()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_and_upload():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing url'}), 400
    url = data['url']
    
    # Download the video
    filename = download480(url)
    print(f"download480 returned filename: {filename}")
    print(f"Files in directory: {os.listdir('.')}")
    if not filename or not os.path.exists(filename):
        return jsonify({'error': f'Download failed. File {filename} not found.'}), 500

    # Upload the video with a unique name
    try:
        base, ext = os.path.splitext(os.path.basename(filename))
        timestamp = int(time.time())
        destination_blob_name = f"{base}_{timestamp}{ext}"
        upload_blob(BUCKET_NAME, filename, destination_blob_name)
        # Delete the local file after upload
        try:
            os.remove(filename)
        except Exception as del_err:
            print(f"Warning: could not delete {filename}: {del_err}")
        return jsonify({'status': 'success', 'uploaded_file': destination_blob_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_direct_stream_url(youtube_url):
    try:
        # First try with cookies
        print(f"Attempting to get direct URL for: {youtube_url}")
        result = subprocess.run(
            ["yt-dlp", "--cookies", "cookies.txt", "-g", youtube_url],
            capture_output=True, text=True, check=True
        )
        urls = result.stdout.strip().split('\n')
        if urls and urls[0]:
            print(f"Successfully got direct URL: {urls[0][:100]}...")
            return urls[0]  # Use the first URL
        else:
            raise Exception("No URLs returned from yt-dlp")
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp error with cookies: {e.stderr}")
        print(f"yt-dlp stdout: {e.stdout}")
        
        # Try without cookies as fallback
        try:
            print("Retrying without cookies...")
            result = subprocess.run(
                ["yt-dlp", "-g", youtube_url],
                capture_output=True, text=True, check=True
            )
            urls = result.stdout.strip().split('\n')
            if urls and urls[0]:
                print(f"Successfully got direct URL without cookies: {urls[0][:100]}...")
                return urls[0]
            else:
                raise Exception("No URLs returned from yt-dlp")
        except subprocess.CalledProcessError as e2:
            print(f"yt-dlp error without cookies: {e2.stderr}")
            print(f"yt-dlp stdout: {e2.stdout}")
            
            # Try updating yt-dlp as last resort
            print("Attempting to update yt-dlp...")
            try:
                subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], check=True)
                print("yt-dlp updated, retrying...")
                result = subprocess.run(
                    ["yt-dlp", "-g", youtube_url],
                    capture_output=True, text=True, check=True
                )
                urls = result.stdout.strip().split('\n')
                if urls and urls[0]:
                    return urls[0]
            except Exception as update_error:
                print(f"Failed to update yt-dlp: {update_error}")
            
            raise Exception(f"Failed to get direct stream URL. Last error: {e2.stderr}")

# Helper: Start ffmpeg chunked download with 30s chunks and title dir
def chunked_download(url, chunk_time=30):
    # Get title and sanitize for directory name
    title = getTitle(url)
    safe_title = "".join(c for c in title if c not in '/\\:*?"<>|').strip() or "video"
    dir_name = safe_title
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    # If YouTube, extract direct stream URL
    if "youtube.com" in url or "youtu.be" in url:
        url = get_direct_stream_url(url)
    chunk_pattern = os.path.join(dir_name, "chunk_%03d.mp4")
    return subprocess.Popen([
        "ffmpeg", "-i", url, "-c", "copy", "-f", "segment",
        "-segment_time", str(chunk_time), chunk_pattern
    ])

# Helper: Background uploader for title dir
def uploader_thread_func(uploaded_chunks, stop_event, dir_name):
    global download_status
    print(f"Uploader thread started for directory: {dir_name}")
    
    while not stop_event.is_set() or any(f.startswith("chunk_") for f in os.listdir(dir_name)):
        for filename in os.listdir(dir_name):
            if filename.startswith("chunk_") and filename.endswith(".mp4") and filename not in uploaded_chunks:
                full_path = os.path.join(dir_name, filename)
                try:
                    print(f"Uploading chunk: {filename}")
                    upload_blob(BUCKET_NAME, full_path, f"{dir_name}/{filename}")
                    os.remove(full_path)
                    uploaded_chunks.add(filename)
                    download_status['total_chunks_uploaded'] += 1
                    print(f"Successfully uploaded and removed: {filename}")
                except Exception as e:
                    print(f"Error uploading chunk {filename}: {e}")
        time.sleep(2)
    
    print(f"Uploader thread finished for directory: {dir_name}")

@app.route('/start_chunked_download', methods=['POST'])
def start_chunked_download():
    global chunked_download_proc, chunked_uploader_thread, uploaded_chunks, chunked_stop_event, download_status
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    
    uploaded_chunks = set()
    chunked_stop_event.clear()
    
    # Get title and safe dir name
    title = getTitle(url)
    safe_title = "".join(c for c in title if c not in '/\\:*?"<>|').strip() or "video"
    dir_name = safe_title
    
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    
    # Update status
    download_status['system_status'] = 'downloading'
    download_status['active_downloads'][dir_name] = {
        'url': url,
        'title': title,
        'start_time': time.time(),
        'total_chunks': 0,
        'uploaded_chunks': 0,
        'remaining_chunks': 0,
        'is_downloading': True,
        'is_uploading': False,
        'progress_percentage': 0.0
    }
    
    chunked_download_proc = chunked_download(url, chunk_time=30)
    chunked_uploader_thread = threading.Thread(target=uploader_thread_func, args=(uploaded_chunks, chunked_stop_event, dir_name))
    chunked_uploader_thread.start()
    
    return jsonify({
        'status': 'started', 
        'directory': dir_name,
        'title': title,
        'message': f'Started downloading {title}'
    })

@app.route('/stop_chunked_download', methods=['POST'])
def stop_chunked_download():
    global chunked_download_proc, chunked_uploader_thread, chunked_stop_event
    if chunked_download_proc:
        chunked_download_proc.terminate()
        chunked_download_proc.wait()
    chunked_stop_event.set()
    if chunked_uploader_thread:
        chunked_uploader_thread.join()
    return jsonify({'status': 'stopped and all chunks uploaded'})

if __name__ == '__main__':
    app.run(debug=True,host="0.0.0.0", port=5000) 