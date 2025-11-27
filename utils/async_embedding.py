import boto3
import json
import time
from botocore.config import Config as BotoConfig
from config import Config

class AsyncNovaEmbedding:
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
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION,
            config=boto_config
        )
        self.model_id = "amazon.nova-2-multimodal-embeddings-v1:0"
        self.bucket_name = Config.S3_BUCKET
    
    def start_async_embedding(self, content_type, s3_uri, text=None, dimension=1024):
        """启动异步embedding生成"""
        try:
            print(f"Debug: [ASYNC 1] Starting async embedding for {content_type}: {s3_uri}")
            
            if content_type == "video":
                model_input = {
                    "taskType": "SEGMENTED_EMBEDDING",
                    "segmentedEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "video": {
                            "format": "mp4",
                            "embeddingMode": "AUDIO_VIDEO_COMBINED",
                            "source": {
                                "s3Location": {
                                    "uri": s3_uri
                                }
                            },
                            "segmentationConfig": {"durationSeconds": 5}
                        }
                    }
                }
            elif content_type == "audio":
                model_input = {
                    "taskType": "SEGMENTED_EMBEDDING",
                    "segmentedEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": dimension,
                        "audio": {
                            "format": "mp3",
                            "source": {
                                "s3Location": {
                                    "uri": s3_uri
                                }
                            },
                            "segmentationConfig": {"durationSeconds": 5}
                        }
                    }
                }
            else:
                raise Exception(f"Async API only supports video and audio, got: {content_type}")
            
            if text:
                model_input["segmentedEmbeddingParams"]["text"] = {
                    "truncationMode": "END",
                    "value": text
                }
            
            print("Debug: [ASYNC 2] Calling start_async_invoke...")
            response = self.bedrock_client.start_async_invoke(
                modelId=self.model_id,
                modelInput=model_input,
                outputDataConfig={
                    "s3OutputDataConfig": {
                        "s3Uri": f"s3://{self.bucket_name}/async-results/"
                    }
                }
            )
            
            invocation_arn = response['invocationArn']
            print(f"Debug: [ASYNC 3] Async job started: {invocation_arn}")
            
            return invocation_arn
            
        except Exception as e:
            print(f"Debug: [ASYNC ERROR] Failed to start async embedding: {str(e)}")
            raise Exception(f"Failed to start async embedding: {str(e)}")
    
    def check_async_status(self, invocation_arn):
        """检查异步任务状态"""
        try:
            print(f"Debug: [STATUS 1] Checking status for: {invocation_arn}")
            
            response = self.bedrock_client.get_async_invoke(
                invocationArn=invocation_arn
            )
            
            status = response['status']
            print(f"Debug: [STATUS 2] Current status: {status}")
            
            return {
                'status': status,
                'response': response
            }
            
        except Exception as e:
            print(f"Debug: [STATUS ERROR] Failed to check status: {str(e)}")
            raise Exception(f"Failed to check async status: {str(e)}")
    
    def get_async_results(self, invocation_arn):
        """获取异步任务结果"""
        try:
            print(f"Debug: [RESULT 1] Getting results for: {invocation_arn}")
            
            # 检查状态
            status_info = self.check_async_status(invocation_arn)
            
            if status_info['status'] != 'Completed':
                return None
            
            # 获取输出S3路径
            output_s3_uri = status_info['response']['outputDataConfig']['s3OutputDataConfig']['s3Uri']
            print(f"Debug: [RESULT 2] Output S3 URI: {output_s3_uri}")
            
            # 解析S3路径获取结果文件
            job_id = invocation_arn.split('/')[-1]
            result_key = f"async-results/{job_id}/segmented-embedding-result.json"
            
            print(f"Debug: [RESULT 3] Loading result from: {result_key}")
            
            # 从S3获取结果
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=result_key
            )
            
            result_data = json.loads(response['Body'].read())
            print(f"Debug: [RESULT 4] Result loaded successfully")
            print(f"Debug: [RESULT 5] Result keys: {list(result_data.keys())}")
            
            # 检查新的Nova格式
            if 'embeddingResults' in result_data:
                print(f"Debug: [RESULT 6] Found Nova format with embeddingResults")
                
                # 获取实际的embedding文件URI
                embedding_result = result_data['embeddingResults'][0]
                if embedding_result['status'] == 'SUCCESS':
                    output_file_uri = embedding_result['outputFileUri']
                    print(f"Debug: [RESULT 7] Loading embeddings from: {output_file_uri}")
                    
                    # 解析S3 URI获取bucket和key
                    uri_parts = output_file_uri.replace('s3://', '').split('/', 1)
                    bucket = uri_parts[0]
                    key = uri_parts[1]
                    
                    # 读取JSONL文件
                    jsonl_response = self.s3_client.get_object(Bucket=bucket, Key=key)
                    jsonl_content = jsonl_response['Body'].read().decode('utf-8')
                    
                    # 解析JSONL格式
                    embeddings = []
                    for line in jsonl_content.strip().split('\n'):
                        if line.strip():
                            segment_data = json.loads(line)
                            if 'embedding' in segment_data:
                                embeddings.append({'embedding': segment_data['embedding']})
                    
                    print(f"Debug: [RESULT 8] Extracted {len(embeddings)} embeddings from JSONL")
                    return {'embeddings': embeddings}
                else:
                    raise Exception(f"Embedding generation failed: {embedding_result}")
            
            # 检查旧格式
            elif 'embeddings' in result_data:
                print(f"Debug: [RESULT 6] Found embeddings array with {len(result_data['embeddings'])} items")
                return result_data
            elif 'segments' in result_data:
                print(f"Debug: [RESULT 6] Found segments array with {len(result_data['segments'])} items")
                embeddings = []
                for segment in result_data['segments']:
                    if 'embedding' in segment:
                        embeddings.append({'embedding': segment['embedding']})
                return {'embeddings': embeddings}
            else:
                print(f"Debug: [RESULT 6] Unexpected result format: {result_data}")
                return result_data
            
        except Exception as e:
            print(f"Debug: [RESULT ERROR] Failed to get results: {str(e)}")
            raise Exception(f"Failed to get async results: {str(e)}")
    
    def wait_for_completion(self, invocation_arn, max_wait_time=1800, check_interval=30):
        """等待异步任务完成"""
        print(f"Debug: [WAIT 1] Waiting for completion, max {max_wait_time}s")
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                status_info = self.check_async_status(invocation_arn)
                status = status_info['status']
                
                if status == 'Completed':
                    print("Debug: [WAIT 2] Task completed successfully")
                    return self.get_async_results(invocation_arn)
                elif status == 'Failed':
                    error_msg = status_info['response'].get('failureMessage', 'Unknown error')
                    raise Exception(f"Async task failed: {error_msg}")
                
                print(f"Debug: [WAIT 3] Status: {status}, waiting {check_interval}s...")
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"Debug: [WAIT ERROR] Error while waiting: {str(e)}")
                raise
        
        raise Exception(f"Async task timeout after {max_wait_time} seconds")
