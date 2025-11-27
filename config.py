import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.environ.get('AWS_REGION') or 'us-east-1'
    S3_BUCKET = os.environ.get('S3_BUCKET') or 'nova-mm-test-bucket'
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {
        'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp'},
        'video': {'mp4', 'avi', 'mov', 'wmv'},
        'audio': {'mp3', 'wav', 'flac', 'm4a'},
        'text': {'txt', 'pdf', 'doc', 'docx'}
    }
