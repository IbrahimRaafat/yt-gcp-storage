from flask import Flask, request, jsonify
from res480Downloader import download480
from upload import upload_blob
import os
import time

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True) 