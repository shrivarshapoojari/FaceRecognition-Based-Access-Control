import firebase_admin
from firebase_admin import credentials, storage, db
from deepface import DeepFace
import os
import time
from PIL import Image
from datetime import datetime
import requests

# Path to your service account key JSON file
service_account_key_path = "service_acc.json"

# Initialize Firebase
cred = credentials.Certificate(service_account_key_path)
firebase_admin.initialize_app(cred, {
    'storageBucket': "facedetection-92a73.appspot.com",
    'databaseURL': 'https://facedetection-92a73-default-rtdb.firebaseio.com'
})

# Get a reference to the storage bucket and database
bucket = storage.bucket()
db_ref = db.reference('1RV22CS211/entry')
logs_ref = db.reference('/logs')

def list_images(folder):
    blobs = bucket.list_blobs(prefix=folder)
    return [blob.name.split("/")[-1] for blob in blobs if blob.name.split("/")[-1]]

def update_access_key(access_value):
    ref = db.reference('1RV22CS211/access')
    ref.set(access_value)

def detect_faces(image_path):
    try:
        img = Image.open(image_path)
        img.verify()
        faces = DeepFace.detectFace(image_path)
        return len(faces) > 0
    except Exception as e:
        print(f"Error in detecting faces: {e}")
        return False

def compare_faces(local_target_image_path, faces_folder):
    if not detect_faces(local_target_image_path):
        print("No face detected in the target image. Waiting...")
        return False

    face_images = list_images(faces_folder)

    for face_image in face_images:
        blob_path = f"{faces_folder}/{face_image}"
        print(f"Attempting to download {blob_path}")
        blob = bucket.blob(blob_path)
        local_face_image_path = f'local_{face_image}'
        blob.download_to_filename(local_face_image_path)

        result = DeepFace.verify(local_target_image_path, local_face_image_path)
        
        os.remove(local_face_image_path)

        if result['verified']:
            return True

    return False

def upload_and_log_image(local_image_path, event_type):
    if not os.path.exists(local_image_path):
        print(f"Error: {local_image_path} does not exist. Cannot upload.")
        return

    try:
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        storage_path = f'images/{timestamp}.jpg'

        print(f"Uploading image to Firebase Storage at path: {storage_path}")
        
        blob = bucket.blob(storage_path)
        blob.upload_from_filename(local_image_path)
        
        blob.make_public()
        print(f"Image made public successfully. Public URL: {blob.public_url}")

        log_entry = {
            'url': blob.public_url,
            'timestamp': timestamp,
            'eventType': event_type
        }
        logs_ref.push(log_entry)
        print(f"Log entry created: {log_entry}")
        
    except Exception as e:
        print(f"Exception occurred during upload or logging: {e}")

def download_image_from_url(url, local_path):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as out_file:
            out_file.write(response.content)
        
        print(f"Image downloaded successfully from {url} to {local_path}")
        return True
    except Exception as e:
        print(f"Failed to download image from {url}: {e}")
        return False

def authenticate_and_update(local_target_image_url, faces_folder):
    local_image_path = 'local_target_image.jpg'

    while True:
        if download_image_from_url(local_target_image_url, local_image_path):
            if not detect_faces(local_image_path):
                print("No face detected in the target image. Retrying in 5 seconds...")
                time.sleep(5)
                continue

            if compare_faces(local_image_path, faces_folder):
                print("Authentication successful. Granting access...")
                update_access_key(1)
                upload_and_log_image(local_image_path, 'Access Granted')
                time.sleep(10)  # Access granted duration
                update_access_key(0)
                print("Access revoked.")
                break
            else:
                print("Authentication failed. Retrying in 5 seconds...")
                upload_and_log_image(local_image_path, 'Access Denied')
                time.sleep(5)
                break
        else:
            print("Failed to download the image. Retrying in 5 seconds...")
            time.sleep(5)

def entry_listener(event):
    if event.data == 1:  # Check if entry is True
        print("Entry detected. Running authentication process...")
        local_target_image_url = 'http://192.168.158.244/cam-lo.jpg'
        faces_folder = "faces"
        authenticate_and_update(local_target_image_url, faces_folder)
    else:
        print(event.data)
        print("No entry detected or entry is False.")

# Set up the listener for changes to the 'entry' key
db_ref.listen(entry_listener)

# Keep the script running to listen for changes
while True:
    time.sleep(1)  # Prevents high CPU usage
