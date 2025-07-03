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

# Set your bucket name here or use an environment variable
BUCKET_NAME = "hidden-matter-450501-n0_cloudbuild"

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
    result = subprocess.run(
        ["yt-dlp", "-g", youtube_url],
        capture_output=True, text=True, check=True
    )
    urls = result.stdout.strip().split('\n')
    return urls[0]  # Use the first URL

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
    while not stop_event.is_set() or any(f.startswith("chunk_") for f in os.listdir(dir_name)):
        for filename in os.listdir(dir_name):
            if filename.startswith("chunk_") and filename.endswith(".mp4") and filename not in uploaded_chunks:
                full_path = os.path.join(dir_name, filename)
                try:
                    upload_blob(BUCKET_NAME, full_path, f"{dir_name}/{filename}")
                    os.remove(full_path)
                    uploaded_chunks.add(filename)
                except Exception as e:
                    print(f"Error uploading chunk {filename}: {e}")
        time.sleep(2)

@app.route('/start_chunked_download', methods=['POST'])
def start_chunked_download():
    global chunked_download_proc, chunked_uploader_thread, uploaded_chunks, chunked_stop_event
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
    chunked_download_proc = chunked_download(url, chunk_time=30)
    chunked_uploader_thread = threading.Thread(target=uploader_thread_func, args=(uploaded_chunks, chunked_stop_event, dir_name))
    chunked_uploader_thread.start()
    return jsonify({'status': 'started', 'directory': dir_name})

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