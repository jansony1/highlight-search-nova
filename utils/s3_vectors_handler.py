import boto3
import json
from botocore.exceptions import ClientError
from config import Config

class S3VectorsHandler:
    def __init__(self):
        # 使用S3 Vectors专用客户端
        self.s3_vectors_client = boto3.client(
            's3vectors',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.vector_bucket_name = Config.S3_BUCKET
        self.vector_index_name = 'nova-multimodal-index'
    
    def create_vector_bucket(self):
        """创建向量存储桶"""
        try:
            self.s3_vectors_client.create_vector_bucket(
                VectorBucketName=self.vector_bucket_name
            )
            print(f"Vector bucket {self.vector_bucket_name} created successfully")
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyExists':
                print(f"Vector bucket {self.vector_bucket_name} already exists")
            else:
                raise Exception(f"Failed to create vector bucket: {str(e)}")
    
    def create_vector_index(self, dimension=1024):
        """创建向量索引"""
        try:
            self.s3_vectors_client.create_vector_index(
                VectorBucketName=self.vector_bucket_name,
                VectorIndexName=self.vector_index_name,
                VectorDimension=dimension
            )
            print(f"Vector index {self.vector_index_name} created successfully")
        except ClientError as e:
            if e.response['Error']['Code'] == 'IndexAlreadyExists':
                print(f"Vector index {self.vector_index_name} already exists")
            else:
                raise Exception(f"Failed to create vector index: {str(e)}")
    
    def put_vector(self, vector_id, vector, metadata=None):
        """存储向量"""
        try:
            request_params = {
                'VectorBucketName': self.vector_bucket_name,
                'VectorIndexName': self.vector_index_name,
                'VectorId': vector_id,
                'Vector': vector
            }
            
            if metadata:
                request_params['Metadata'] = metadata
            
            self.s3_vectors_client.put_vector(**request_params)
            print(f"Vector {vector_id} stored successfully")
        except ClientError as e:
            raise Exception(f"Failed to store vector: {str(e)}")
    
    def query_vectors(self, query_vector, max_results=10, include_metadata=True):
        """查询相似向量"""
        try:
            request_params = {
                'VectorBucketName': self.vector_bucket_name,
                'VectorIndexName': self.vector_index_name,
                'QueryVector': query_vector,
                'MaxResults': max_results,
                'IncludeMetadata': include_metadata,
                'IncludeDistance': True
            }
            
            response = self.s3_vectors_client.query_vectors(**request_params)
            return response.get('Vectors', [])
        except ClientError as e:
            raise Exception(f"Failed to query vectors: {str(e)}")
    
    def delete_vector(self, vector_id):
        """删除向量"""
        try:
            self.s3_vectors_client.delete_vector(
                VectorBucketName=self.vector_bucket_name,
                VectorIndexName=self.vector_index_name,
                VectorId=vector_id
            )
            print(f"Vector {vector_id} deleted successfully")
        except ClientError as e:
            raise Exception(f"Failed to delete vector: {str(e)}")
