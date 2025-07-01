from google.cloud import storage

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    # Ensure destination_blob_name is a proper file path *within* the bucket.
    # For example: "source/my_file.txt"
    blob = bucket.blob(destination_blob_name)

    try:
        blob.upload_from_filename(source_file_name)
        print(
            f"File {source_file_name} uploaded to gs://{bucket_name}/{destination_blob_name}."
        )
    except Exception as e:
        print(f"Error uploading file: {e}")
        return


