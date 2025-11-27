import numpy as np
import json
import boto3
from botocore.exceptions import ClientError
from utils.s3_handler import S3Handler
from config import Config
from typing import List, Dict, Optional

class DimensionAwareVectorSearch:
    """按维度分库的向量搜索系统"""
    
    def __init__(self):
        self.s3_handler = S3Handler()
        # 按维度分组存储向量 {dimension: {id: vector}}
        self.vectors_by_dimension = {
            256: {},
            384: {},
            1024: {},
            3072: {}
        }
        # 统一的元数据存储 {id: metadata}
        self.metadata = {}
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET
    
    def add_vector(self, id: str, vector: List[float], metadata: Dict):
        """添加向量，自动按维度分类存储"""
        # 验证向量有效性
        if not vector or len(vector) == 0:
            raise Exception("Vector is empty")
        
        if not any(x != 0 for x in vector):
            raise Exception("Vector contains all zeros")
        
        dimension = len(vector)
        if dimension not in self.vectors_by_dimension:
            raise Exception(f"Unsupported dimension: {dimension}. Supported: {list(self.vectors_by_dimension.keys())}")
        
        # 检查向量长度合理
        if dimension < 100:
            raise Exception(f"Vector dimension too small: {dimension}")
        
        # 添加到对应维度的内存存储
        self.vectors_by_dimension[dimension][id] = vector
        
        # 添加维度信息到元数据
        metadata_with_dim = {**metadata, 'dimension': dimension}
        self.metadata[id] = metadata_with_dim
        
        # 保存到S3（按维度分目录）
        vector_data = {
            'id': id,
            'vector': vector,
            'metadata': metadata_with_dim
        }
        
        try:
            # 新的S3路径：vectors/{dimension}/{id}.json
            s3_key = f"vectors/{dimension}/{id}.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(vector_data),
                ContentType='application/json'
            )
            print(f"Debug: Vector {id} (dim={dimension}) saved to S3: {s3_key}")
        except Exception as e:
            # 如果S3保存失败，从内存中移除
            if id in self.vectors_by_dimension[dimension]:
                del self.vectors_by_dimension[dimension][id]
            if id in self.metadata:
                del self.metadata[id]
            raise Exception(f"Failed to save vector to S3: {str(e)}")
    
    def search(self, query_vector: List[float], top_k: int = 5, 
               target_dimension: Optional[int] = None) -> List[Dict]:
        """
        搜索向量
        
        Args:
            query_vector: 查询向量
            top_k: 返回结果数量
            target_dimension: 指定搜索维度，None表示自动检测
        """
        query_dimension = len(query_vector)
        
        # 如果指定了目标维度，验证查询向量维度是否匹配
        if target_dimension is not None:
            if query_dimension != target_dimension:
                raise Exception(f"Query vector dimension ({query_dimension}) doesn't match target dimension ({target_dimension})")
            search_dimension = target_dimension
        else:
            # 自动检测：使用查询向量的维度
            search_dimension = query_dimension
        
        print(f"Debug: [SEARCH 1] Searching in dimension {search_dimension} with {len(query_vector)}D query vector")
        
        # 确保该维度的向量已加载
        if not self.vectors_by_dimension[search_dimension]:
            print(f"Debug: [SEARCH 2] No vectors in memory for dimension {search_dimension}, loading from S3...")
            self.load_vectors_by_dimension(search_dimension)
            print(f"Debug: [SEARCH 2.1] Loaded {len(self.vectors_by_dimension[search_dimension])} vectors for dimension {search_dimension}")
        
        vectors = self.vectors_by_dimension[search_dimension]
        if not vectors:
            print(f"Debug: [SEARCH 3] No vectors found for dimension {search_dimension}")
            return []
        
        print(f"Debug: [SEARCH 3] Starting similarity calculation for {len(vectors)} vectors in dimension {search_dimension}")
        similarities = []
        
        for i, (id, vector) in enumerate(vectors.items()):
            try:
                similarity = self.cosine_similarity(query_vector, vector)
                if not (np.isnan(similarity) or np.isinf(similarity)):
                    similarities.append({
                        'id': id,
                        'similarity': similarity,
                        'metadata': self.metadata.get(id, {})
                    })
                    print(f"Debug: [SEARCH 3.{i+1}] Valid similarity for {id}: {similarity:.4f}")
                else:
                    print(f"Debug: [SEARCH 3.{i+1}] Invalid similarity for {id}: {similarity}")
            except Exception as e:
                print(f"Debug: [SEARCH 3.{i+1}] Error calculating similarity for {id}: {str(e)}")
        
        print("Debug: [SEARCH 4] Sorting results by similarity...")
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        result = similarities[:top_k]
        print(f"Debug: [SEARCH 5] Found {len(result)} valid similar vectors in dimension {search_dimension}")
        return result
    
    def load_vectors_by_dimension(self, dimension: int):
        """加载指定维度的所有向量"""
        try:
            print(f"Debug: [S3 1] Loading vectors for dimension {dimension}...")
            
            # 列出指定维度目录下的所有向量文件
            prefix = f"vectors/{dimension}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                print(f"Debug: [S3 2] No vector files found for dimension {dimension}")
                return
            
            print(f"Debug: [S3 2] Found {len(response['Contents'])} objects for dimension {dimension}")
            
            for i, obj in enumerate(response['Contents'], 1):
                key = obj['Key']
                if key.endswith('.json'):
                    try:
                        print(f"Debug: [S3 3.{i}] Loading vector from {key}...")
                        response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=key
                        )
                        
                        vector_data = json.loads(response['Body'].read())
                        
                        # 添加到内存
                        id = vector_data['id']
                        self.vectors_by_dimension[dimension][id] = vector_data['vector']
                        self.metadata[id] = vector_data['metadata']
                        print(f"Debug: [S3 3.{i}] Vector {id} loaded successfully")
                        
                    except Exception as e:
                        print(f"Debug: [S3 3.{i}] Error loading vector from {key}: {str(e)}")
            
            print(f"Debug: [S3 4] Completed loading {len(self.vectors_by_dimension[dimension])} vectors for dimension {dimension}")
            
        except Exception as e:
            print(f"Debug: [S3 ERROR] Error loading vectors for dimension {dimension}: {str(e)}")
    
    def load_all_vectors(self):
        """加载所有维度的向量（向后兼容）"""
        for dimension in self.vectors_by_dimension.keys():
            self.load_vectors_by_dimension(dimension)
    
    def get_dimension_stats(self) -> Dict[int, int]:
        """获取各维度的向量数量统计"""
        # 先尝试从内存获取
        stats = {
            dim: len(vectors) 
            for dim, vectors in self.vectors_by_dimension.items()
        }
        
        # 如果内存中没有数据，从S3获取统计
        if sum(stats.values()) == 0:
            try:
                for dimension in self.vectors_by_dimension.keys():
                    prefix = f"vectors/{dimension}/"
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.bucket_name,
                        Prefix=prefix
                    )
                    stats[dimension] = len(response.get('Contents', []))
            except Exception as e:
                print(f"Debug: Error getting dimension stats from S3: {str(e)}")
        
        return stats
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = np.dot(vec1, vec2) / (norm1 * norm2)
        
        if np.isnan(similarity) or np.isinf(similarity):
            return 0.0
        
        return float(similarity)
    
    # 向后兼容方法
    def detect_vector_dimension(self) -> int:
        """检测最常见的向量维度（向后兼容）"""
        stats = self.get_dimension_stats()
        if not any(stats.values()):
            return 1024  # 默认维度
        
        most_common_dim = max(stats, key=stats.get)
        print(f"Debug: [DIMENSION] Dimension statistics: {stats}")
        print(f"Debug: [DIMENSION] Most common dimension: {most_common_dim}")
        return most_common_dim
