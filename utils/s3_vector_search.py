from utils.s3_vectors_handler import S3VectorsHandler

class S3VectorSearch:
    def __init__(self):
        self.s3_vectors = S3VectorsHandler()
        self._ensure_setup()
    
    def _ensure_setup(self):
        """确保向量存储桶和索引已创建"""
        try:
            self.s3_vectors.create_vector_bucket()
            self.s3_vectors.create_vector_index()
        except Exception as e:
            print(f"Setup warning: {str(e)}")
    
    def add_vector(self, id, vector, metadata):
        """添加向量到S3 Vectors"""
        if not vector or len(vector) == 0:
            raise Exception("Vector is empty")
        
        if not any(x != 0 for x in vector):
            raise Exception("Vector contains all zeros")
        
        try:
            self.s3_vectors.put_vector(id, vector, metadata)
            print(f"Vector {id} added to S3 Vectors")
        except Exception as e:
            raise Exception(f"Failed to add vector: {str(e)}")
    
    def search(self, query_vector, top_k=5):
        """使用S3 Vectors进行搜索"""
        try:
            results = self.s3_vectors.query_vectors(query_vector, max_results=top_k)
            
            # 转换结果格式以保持兼容性
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'id': result['VectorId'],
                    'similarity': 1 - result.get('Distance', 0),  # 距离转相似度
                    'metadata': result.get('Metadata', {})
                })
            
            print(f"Found {len(formatted_results)} similar vectors")
            return formatted_results
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def delete_vector(self, id):
        """删除向量"""
        try:
            self.s3_vectors.delete_vector(id)
        except Exception as e:
            raise Exception(f"Failed to delete vector: {str(e)}")
