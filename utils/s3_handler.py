import boto3
import json
from botocore.exceptions import ClientError
from config import Config

class S3Handler:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET
    
    def upload_file(self, file_obj, key):
        try:
            self.s3_client.upload_fileobj(file_obj, self.bucket_name, key)
            return f"s3://{self.bucket_name}/{key}"
        except ClientError as e:
            raise Exception(f"S3 upload failed: {str(e)}")
    
    def download_file(self, key, local_path):
        try:
            self.s3_client.download_file(self.bucket_name, key, local_path)
            return local_path
        except ClientError as e:
            raise Exception(f"S3 download failed: {str(e)}")
    
    def save_vector(self, key, vector_data):
        try:
            vector_json = json.dumps(vector_data)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"vectors/{key}.json",
                Body=vector_json,
                ContentType='application/json'
            )
            return f"s3://{self.bucket_name}/vectors/{key}.json"
        except ClientError as e:
            raise Exception(f"Vector save failed: {str(e)}")
    
    def load_vector(self, key):
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=f"vectors/{key}.json"
            )
            return json.loads(response['Body'].read())
        except ClientError as e:
            raise Exception(f"Vector load failed: {str(e)}")
