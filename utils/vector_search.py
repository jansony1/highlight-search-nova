import numpy as np
import json
import boto3
from botocore.exceptions import ClientError
from utils.s3_handler import S3Handler
from config import Config

class VectorSearch:
    def __init__(self):
        self.s3_handler = S3Handler()
        self.vectors = {}
        self.metadata = {}
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET
    
    def detect_vector_dimension(self):
        """检测存储向量的维度，使用最常见的维度"""
        try:
            # 如果内存中没有向量，先加载
            if not self.vectors:
                self.load_all_vectors()
            
            if self.vectors:
                # 统计所有向量的维度
                dimension_counts = {}
                for vector in self.vectors.values():
                    dim = len(vector)
                    dimension_counts[dim] = dimension_counts.get(dim, 0) + 1
                
                # 找到最常见的维度
                most_common_dim = max(dimension_counts, key=dimension_counts.get)
                total_vectors = len(self.vectors)
                
                print(f"Debug: [DIMENSION] Dimension statistics: {dimension_counts}")
                print(f"Debug: [DIMENSION] Most common dimension: {most_common_dim} ({dimension_counts[most_common_dim]}/{total_vectors} vectors)")
                
                return most_common_dim
            else:
                print("Debug: [DIMENSION] No vectors found, using default dimension 1024")
                return 1024  # 默认维度
                
        except Exception as e:
            print(f"Debug: [DIMENSION ERROR] Failed to detect dimension: {str(e)}")
            return 1024  # 出错时使用默认维度

    def cosine_similarity(self, vec1, vec2):
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        # 计算向量范数
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        # 避免除零错误
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        # 计算余弦相似度
        similarity = np.dot(vec1, vec2) / (norm1 * norm2)
        
        # 确保结果在有效范围内，避免NaN
        if np.isnan(similarity) or np.isinf(similarity):
            return 0.0
        
        return float(similarity)
    
    def add_vector(self, id, vector, metadata):
        # 验证向量有效性
        if not vector or len(vector) == 0:
            raise Exception("Vector is empty")
        
        # 检查向量不全为0
        if not any(x != 0 for x in vector):
            raise Exception("Vector contains all zeros")
        
        # 检查向量长度合理
        if len(vector) < 100:  # 假设embedding至少应该有100维
            raise Exception(f"Vector dimension too small: {len(vector)}")
        
        self.vectors[id] = vector
        self.metadata[id] = metadata
        
        # Save to S3
        vector_data = {
            'id': id,
            'vector': vector,
            'metadata': metadata
        }
        
        try:
            self.s3_handler.save_vector(id, vector_data)
            print(f"Debug: Vector {id} added to search index and saved to S3")
        except Exception as e:
            # 如果S3保存失败，从内存中移除
            if id in self.vectors:
                del self.vectors[id]
            if id in self.metadata:
                del self.metadata[id]
            raise Exception(f"Failed to save vector to S3: {str(e)}")
    
    def search(self, query_vector, top_k=5):
        print(f"Debug: [SEARCH 1] Starting search with {len(self.vectors)} vectors in memory")
        
        if not self.vectors:
            print("Debug: [SEARCH 2] No vectors in memory, loading from S3...")
            self.load_all_vectors()
            print(f"Debug: [SEARCH 2.1] Loaded {len(self.vectors)} vectors from S3")
        
        if not self.vectors:
            print("Debug: [SEARCH 3] No vectors found after loading from S3")
            return []
        
        print(f"Debug: [SEARCH 3] Starting similarity calculation for {len(self.vectors)} vectors")
        similarities = []
        for i, (id, vector) in enumerate(self.vectors.items()):
            try:
                print(f"Debug: [SEARCH 3.{i+1}] Calculating similarity for vector {id}")
                similarity = self.cosine_similarity(query_vector, vector)
                # 确保相似度是有效数值
                if not (np.isnan(similarity) or np.isinf(similarity)):
                    similarities.append({
                        'id': id,
                        'similarity': float(similarity),
                        'metadata': self.metadata[id]
                    })
                    print(f"Debug: [SEARCH 3.{i+1}] Valid similarity: {similarity:.4f}")
                else:
                    print(f"Debug: [SEARCH 3.{i+1}] Invalid similarity for {id}: {similarity}")
            except Exception as e:
                print(f"Debug: [SEARCH 3.{i+1}] Error calculating similarity for {id}: {str(e)}")
        
        print("Debug: [SEARCH 4] Sorting results by similarity...")
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        result = similarities[:top_k]
        print(f"Debug: [SEARCH 5] Found {len(result)} valid similar vectors")
        return result
    
    def load_all_vectors(self):
        try:
            print("Debug: [S3 1] Starting to load vectors from S3...")
            # List all vector files in S3
            print("Debug: [S3 2] Listing objects in S3 bucket...")
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix='vectors/'
            )
            print("Debug: [S3 2.1] S3 list_objects_v2 completed")
            
            if 'Contents' not in response:
                print("Debug: [S3 3] No vector files found in S3")
                return
            
            print(f"Debug: [S3 3] Found {len(response['Contents'])} objects in S3")
            
            for i, obj in enumerate(response['Contents']):
                key = obj['Key']
                if key.endswith('.json'):
                    try:
                        print(f"Debug: [S3 4.{i+1}] Loading vector from {key}...")
                        # Load vector data
                        response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=key
                        )
                        print(f"Debug: [S3 4.{i+1}.1] S3 get_object completed for {key}")
                        
                        vector_data = json.loads(response['Body'].read())
                        print(f"Debug: [S3 4.{i+1}.2] JSON parsing completed for {key}")
                        
                        # Add to memory
                        id = vector_data['id']
                        self.vectors[id] = vector_data['vector']
                        self.metadata[id] = vector_data['metadata']
                        print(f"Debug: [S3 4.{i+1}.3] Vector {id} added to memory")
                        
                    except Exception as e:
                        print(f"Debug: [S3 4.{i+1}.ERROR] Error loading vector from {key}: {str(e)}")
            
            print(f"Debug: [S3 5] Completed loading {len(self.vectors)} vectors from S3")
            
        except Exception as e:
            print(f"Debug: [S3 ERROR] Error loading vectors from S3: {str(e)}")
