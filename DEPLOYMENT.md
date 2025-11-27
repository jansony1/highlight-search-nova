# 部署指南

## 本地开发环境

### 1. 环境准备
```bash
# 克隆项目
git clone <repository-url>
cd nova_mm

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. AWS配置
```bash
# 配置AWS凭证
cp .env.example .env
# 编辑 .env 文件填入AWS凭证

# 创建S3存储桶
aws s3 mb s3://nova-mm-test-bucket --region us-east-1
```

### 3. 启动应用
```bash
python app.py
```

## 生产环境部署

### 使用Gunicorn
```bash
# 安装Gunicorn
pip install gunicorn

# 启动应用
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### AWS ECS部署
1. 构建Docker镜像并推送到ECR
2. 创建ECS任务定义
3. 配置环境变量
4. 部署到ECS集群

## 环境变量配置

### 必需变量
- `AWS_ACCESS_KEY_ID`: AWS访问密钥
- `AWS_SECRET_ACCESS_KEY`: AWS秘密密钥
- `AWS_REGION`: AWS区域
- `S3_BUCKET`: S3存储桶名称

### 可选变量
- `SECRET_KEY`: Flask密钥
- `MAX_CONTENT_LENGTH`: 最大文件大小

## 安全配置

### 1. IAM权限
最小权限原则，仅授予必要的S3和Bedrock权限：
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::nova-mm-test-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2. 网络安全
- 使用HTTPS
- 配置防火墙规则
- 启用访问日志

## 监控和日志

### 1. 应用日志
```python
import logging
logging.basicConfig(level=logging.INFO)
```

### 2. AWS CloudWatch
- 配置日志组
- 设置指标和告警
- 监控API调用

## 故障排除

### 常见问题
1. **AWS凭证错误**: 检查环境变量配置
2. **S3权限问题**: 验证IAM策略
3. **Bedrock访问**: 确认区域和模型可用性
4. **文件上传失败**: 检查文件大小和格式
