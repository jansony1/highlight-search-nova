import boto3
import base64
import json
from botocore.config import Config as BotoConfig
from config import Config

class NovaEmbedding:
    def __init__(self):
        # 配置更长的超时时间
        boto_config = BotoConfig(
            read_timeout=300,  # 5分钟读取超时
            connect_timeout=60,  # 1分钟连接超时
            retries={'max_attempts': 3}
        )
        
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION,
            config=boto_config
        )
        self.model_id = "amazon.nova-2-multimodal-embeddings-v1:0"
    
    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def encode_video(self, video_path):
        with open(video_path, "rb") as video_file:
            return base64.b64encode(video_file.read()).decode('utf-8')
    
    def encode_audio(self, audio_path):
        with open(audio_path, "rb") as audio_file:
            return base64.b64encode(audio_file.read()).decode('utf-8')
    
    def generate_embedding(self, content_type, content, text=None, dimension=1024):
        try:
            print(f"Debug: [EMBEDDING 1] Starting embedding generation for type: {content_type}, dimension: {dimension}")
            
            if content_type == "text":
                print("Debug: [EMBEDDING 2.1] Building text embedding request...")
                body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "text": {
                            "truncationMode": "END",
                            "value": content
                        }
                    }
                }
            elif content_type == "image":
                print("Debug: [EMBEDDING 2.2] Building image embedding request...")
                body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "image": {
                            "format": "jpeg",
                            "source": {
                                "bytes": content
                            }
                        }
                    }
                }
                if text:
                    body["singleEmbeddingParams"]["text"] = {
                        "truncationMode": "END",
                        "value": text
                    }
            elif content_type == "video":
                print("Debug: [EMBEDDING 2.3] Building video embedding request...")
                print("Debug: [EMBEDDING 2.3.1] Note: Sync API supports up to 30 seconds of video")
                
                body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "video": {
                            "format": "mp4",
                            "embeddingMode": "AUDIO_VIDEO_COMBINED",
                            "source": {
                                "bytes": content
                            }
                        }
                    }
                }
                if text:
                    body["singleEmbeddingParams"]["text"] = {
                        "truncationMode": "END",
                        "value": text
                    }
            elif content_type == "audio":
                print("Debug: [EMBEDDING 2.4] Building audio embedding request...")
                print("Debug: [EMBEDDING 2.4.1] Note: Sync API supports up to 30 seconds of audio")
                
                body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "audio": {
                            "format": "mp3",
                            "source": {
                                "bytes": content
                            }
                        }
                    }
                }
                if text:
                    body["singleEmbeddingParams"]["text"] = {
                        "truncationMode": "END",
                        "value": text
                    }
            else:
                raise Exception(f"Unsupported content type: {content_type}")
            
            print(f"Debug: [EMBEDDING 3] Request body prepared, calling Bedrock with model {self.model_id}")
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json"
            )
            
            print("Debug: [EMBEDDING 4] Bedrock API call completed, parsing response...")
            
            result = json.loads(response['body'].read())
            embedding = result['embeddings'][0]['embedding']
            
            print(f"Debug: [EMBEDDING 5] Embedding extraction completed, length: {len(embedding)}")
            return embedding
            
        except Exception as e:
            print(f"Debug: [EMBEDDING ERROR] Embedding generation failed: {str(e)}")
            # 如果是"Input is too long"错误，提供正确的解决方案
            if "Input is too long" in str(e):
                raise Exception(f"Content too long for sync API. For videos/audio >30s, use async API with S3. Original error: {str(e)}")
            raise Exception(f"Embedding generation failed: {str(e)}")
