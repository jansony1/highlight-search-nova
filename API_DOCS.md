# API 文档

## 概述
Amazon Nova Multimodal Embedding 测试网站的RESTful API文档。

## 基础信息
- **Base URL**: `http://localhost:5000`
- **Content-Type**: `application/json` (除文件上传外)

## 端点

### 1. 主页面
```
GET /
```
返回主页面HTML。

### 2. 文件上传和Embedding生成
```
POST /api/upload
```

**请求参数** (multipart/form-data):
- `file`: 文件对象 (必需)
- `type`: 文件类型 - "image", "video", "audio", "text" (必需)
- `text`: 描述文本 (可选)

**响应示例**:
```json
{
  "success": true,
  "file_id": "uuid-string",
  "message": "File uploaded and processed successfully"
}
```

**错误响应**:
```json
{
  "error": "Error message"
}
```

### 3. 向量搜索
```
POST /api/search
```

**请求体**:
```json
{
  "query": "搜索文本",
  "top_k": 5
}
```

**响应示例**:
```json
{
  "success": true,
  "results": [
    {
      "id": "file-id",
      "similarity": 0.95,
      "metadata": {
        "filename": "example.jpg",
        "file_type": "image",
        "s3_url": "s3://bucket/path",
        "text": "描述文本"
      }
    }
  ]
}
```

## 错误代码
- `400`: 请求参数错误
- `500`: 服务器内部错误

## 文件限制
- 最大文件大小: 100MB
- 支持格式:
  - 图像: PNG, JPG, JPEG, GIF, BMP
  - 视频: MP4, AVI, MOV, WMV
  - 音频: MP3, WAV, FLAC, M4A
  - 文本: TXT, PDF, DOC, DOCX
