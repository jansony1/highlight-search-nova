import boto3
import json
import base64
import subprocess
import os
import uuid
from pathlib import Path
from config import Config
import numpy as np

class HighlightExtractor:
    def __init__(self):
        self.bedrock = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET

    def generate_criteria(self, theme):
        """
        步骤1: 使用Claude Opus 4.5根据用户主题改写高光判定标准
        """
        prompt = f"""请根据用户提供的主题，改写视频高光片段判定标准。

用户主题：{theme}

原始标准模板：
## 高光片段判定标准：
- 动作精彩或技巧性强的时刻
- 情感表达丰富或戏剧性的瞬间
- 关键转折点或重要事件
- 视觉效果突出或构图优美的片段
- 具有故事性或叙事价值的时刻

请根据用户的主题，保持相同的格式（使用 - 符号作为列表项），但改写判定标准的具体内容，使其更贴合用户想要提取的高光场景。
只输出改写后的标准，保持markdown格式。"""

        try:
            response = self.bedrock.invoke_model(
                modelId="global.anthropic.claude-opus-4-5-20251101-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )

            result = json.loads(response['body'].read())
            criteria = result['content'][0]['text']
            return criteria

        except Exception as e:
            print(f"[步骤1] 生成标准失败: {str(e)}")
            import traceback
            traceback.print_exc()
            # 如果失败，返回默认标准
            return """## 高光片段判定标准：
- 动作精彩或技巧性强的时刻
- 情感表达丰富或戏剧性的瞬间
- 关键转折点或重要事件
- 视觉效果突出或构图优美的片段
- 具有故事性或叙事价值的时刻"""

    def compress_video(self, input_path, output_path, max_size_mb=100):
        """
        步骤2: 使用FFmpeg智能压缩视频

        压缩策略：
        1. 如果原视频 <= 25MB: 不压缩，直接使用
        2. 如果原视频 25-100MB: 使用CRF质量控制，保持高质量
        3. 如果原视频 > 100MB: 压缩到目标大小(默认100MB)
        """
        try:
            # 获取原视频信息
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=size,duration',
                '-of', 'json',
                input_path
            ]
            probe_result = subprocess.check_output(probe_cmd).decode()
            probe_data = json.loads(probe_result)

            original_size = int(probe_data['format']['size']) / (1024 * 1024)  # MB
            duration = float(probe_data['format']['duration'])

            print(f"[压缩] 原视频大小: {original_size:.2f} MB, 时长: {duration:.2f}秒")

            # 策略1: 小文件不压缩
            if original_size <= 25:
                print(f"[压缩] 文件较小({original_size:.2f}MB)，跳过压缩")
                return input_path

            # 策略2: 中等文件 - 直接跳过压缩或轻度压缩
            elif original_size <= max_size_mb:
                # Nova Pro支持最大100MB，如果已经在范围内就不压缩
                print(f"[压缩] 文件大小适中({original_size:.2f}MB)，跳过压缩以避免增大")
                return input_path

            # 策略3: 大文件压缩到目标大小
            else:
                target_bitrate = int((max_size_mb * 8 * 1024) / duration) - 128
                print(f"[压缩] 大文件压缩到目标大小 ({original_size:.2f}MB -> {max_size_mb}MB)")
                print(f"[压缩] 目标比特率: {target_bitrate}kbps")

                compress_cmd = [
                    'ffmpeg', '-i', input_path,
                    '-c:v', 'libx264',
                    '-b:v', f'{target_bitrate}k',
                    '-maxrate', f'{int(target_bitrate * 1.5)}k',
                    '-bufsize', f'{target_bitrate * 2}k',
                    '-preset', 'medium',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-y', output_path
                ]

            # 执行压缩
            result = subprocess.run(compress_cmd, check=True, capture_output=True, text=True)

            # 检查输出文件大小
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path) / (1024 * 1024)
                compression_ratio = (1 - output_size / original_size) * 100
                print(f"[压缩] 压缩完成: {output_size:.2f}MB (压缩率: {compression_ratio:.1f}%)")
                return output_path
            else:
                print(f"[压缩] 输出文件不存在，使用原文件")
                return input_path

        except Exception as e:
            print(f"[压缩] 压缩失败: {str(e)}")
            # 如果压缩失败，返回原视频
            return input_path

    def analyze_video(self, video_path, criteria):
        """
        步骤3: 使用Nova Pro模型分析视频并生成高光要点

        策略：
        1. 视频 < 25MB: 使用base64 inline分析
        2. 视频 >= 25MB: 上传到S3，使用S3 URI分析（支持最大1GB）
        """
        try:
            # 检查视频大小
            file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
            duration = self.get_video_duration(video_path)

            print(f"[分析] 视频大小: {file_size:.2f}MB, 时长: {duration:.2f}秒")

            # 如果视频较小，使用inline base64
            if file_size < 25:
                print(f"[分析] 视频较小，使用inline base64分析")
                return self._analyze_single_video_inline(video_path, criteria)

            # 否则上传到S3使用URI分析
            print(f"[分析] 视频较大({file_size:.2f}MB)，上传到S3使用URI分析")
            return self._analyze_video_via_s3(video_path, criteria)

        except Exception as e:
            print(f"Error analyzing video: {str(e)}")
            raise

    def _analyze_single_video_inline(self, video_path, criteria):
        """使用base64 inline方式分析视频（<25MB）"""
        with open(video_path, 'rb') as f:
            video_base64 = base64.b64encode(f.read()).decode('utf-8')

        prompt = f"""请分析这个视频并提炼高光要点。

{criteria}

## 输出要求：
请按以下格式输出高光要点，每个要点包含优先级（1=最重要，2=重要，3=一般）：

**视频总结：**
[简要描述视频的整体内容和主题]

**高光要点列表：**
A. [优先级1] - [具体的高光内容描述]
B. [优先级2] - [具体的高光内容描述]
C. [优先级1] - [具体的高光内容描述]
...

请确保：
1. 按视频时间顺序排列要点
2. 每个要点都有明确的优先级标记
3. 描述具体且便于后续匹配
4. 重点关注真正精彩的时刻，而非简单概括"""

        response = self.bedrock.invoke_model(
            modelId="amazon.nova-pro-v1:0",
            body=json.dumps({
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "video": {
                                "format": "mp4",
                                "source": {"bytes": video_base64}
                            }
                        },
                        {"text": prompt}
                    ]
                }],
                "inferenceConfig": {
                    "max_new_tokens": 2000
                }
            })
        )

        result = json.loads(response['body'].read())
        analysis = result['output']['message']['content'][0]['text']
        return analysis

    def _analyze_video_via_s3(self, video_path, criteria):
        """使用S3 URI方式分析视频（>=25MB）"""
        # 生成唯一的S3 key
        video_filename = os.path.basename(video_path)
        s3_key = f"videos/temp/{uuid.uuid4()}_{video_filename}"

        try:
            # 上传视频到S3
            print(f"[分析] 上传视频到S3: {s3_key}")
            with open(video_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ContentType': 'video/mp4'}
                )

            # 构建S3 URI
            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            print(f"[分析] S3 URI: {s3_uri}")

            # 使用S3 URI调用Nova Pro
            prompt = f"""请分析这个视频并提炼高光要点。

{criteria}

## 输出要求：
请按以下格式输出高光要点，每个要点包含优先级（1=最重要，2=重要，3=一般）：

**视频总结：**
[简要描述视频的整体内容和主题]

**高光要点列表：**
A. [优先级1] - [具体的高光内容描述]
B. [优先级2] - [具体的高光内容描述]
C. [优先级1] - [具体的高光内容描述]
...

请确保：
1. 按视频时间顺序排列要点
2. 每个要点都有明确的优先级标记
3. 描述具体且便于后续匹配
4. 重点关注真正精彩的时刻，而非简单概括"""

            response = self.bedrock.invoke_model(
                modelId="amazon.nova-pro-v1:0",
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "video": {
                                    "format": "mp4",
                                    "source": {"s3Location": {"uri": s3_uri}}
                                }
                            },
                            {"text": prompt}
                        ]
                    }],
                    "inferenceConfig": {
                        "max_new_tokens": 2000
                    }
                })
            )

            result = json.loads(response['body'].read())
            analysis = result['output']['message']['content'][0]['text']

            # 删除临时S3文件
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                print(f"[分析] 已删除临时S3文件: {s3_key}")
            except Exception as e:
                print(f"[分析] 警告：删除临时S3文件失败: {str(e)}")

            return analysis

        except Exception as e:
            # 如果出错，尝试清理S3文件
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            except:
                pass
            raise


    def extract_clips_with_embeddings(self, video_path, segment_duration=3):
        """
        步骤4: 使用Nova MME的inline分片功能生成向量嵌入

        重要：不使用FFmpeg切片，直接使用Nova MME的SEGMENTED_EMBEDDING API
        """
        try:
            # 获取视频时长
            duration = self.get_video_duration(video_path)
            file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB

            print(f"[向量生成] 视频时长: {duration:.2f}秒, 大小: {file_size:.2f}MB")
            print(f"[向量生成] 使用Nova MME inline分段，每段 {segment_duration} 秒")

            # 检查文件大小，决定使用inline还是S3方式
            if file_size < 25:
                print(f"[向量生成] 使用inline base64方式")
                segments_data = self._generate_segmented_embeddings_inline(video_path, segment_duration)
            else:
                print(f"[向量生成] 使用S3 URI方式")
                segments_data = self._generate_segmented_embeddings_s3(video_path, segment_duration)

            # 优化：不预先提取所有clip，只保存元数据
            # 在匹配后再提取需要的clip
            output_dir = os.path.join('static', 'clips', str(uuid.uuid4()))
            os.makedirs(output_dir, exist_ok=True)

            clips = []
            for i, seg in enumerate(segments_data):
                timestamp = i * segment_duration

                clips.append({
                    'video_source': video_path,  # 保存原视频路径
                    'output_dir': output_dir,    # 保存输出目录
                    'timestamp': timestamp,
                    'duration': segment_duration,
                    'index': i,
                    'embedding': seg['embedding'],
                    'path': None  # 暂时不生成实际文件
                })

            print(f"[向量生成] 完成！共 {len(clips)} 个片段的向量")
            return clips

        except Exception as e:
            print(f"[向量生成] 错误: {str(e)}")
            raise

    def _generate_segmented_embeddings_inline(self, video_path, segment_duration):
        """使用inline base64方式生成分段嵌入"""
        with open(video_path, 'rb') as f:
            video_base64 = base64.b64encode(f.read()).decode('utf-8')

        request_body = {
            "taskType": "SEGMENTED_EMBEDDING",
            "segmentedEmbeddingParams": {
                "embeddingPurpose": "GENERIC_INDEX",
                "embeddingDimension": 1024,
                "video": {
                    "format": "mp4",
                    "embeddingMode": "AUDIO_VIDEO_COMBINED",
                    "source": {"bytes": video_base64},
                    "segmentationConfig": {"durationSeconds": segment_duration}
                }
            }
        }

        response = self.bedrock.invoke_model(
            modelId="amazon.nova-2-multimodal-embeddings-v1:0",
            body=json.dumps(request_body)
        )

        result = json.loads(response['body'].read())
        return result['embeddings']

    def _generate_segmented_embeddings_s3(self, video_path, segment_duration):
        """使用S3 URI方式生成分段嵌入（异步API）"""
        import time

        # 生成唯一的S3 key
        video_filename = os.path.basename(video_path)
        s3_key = f"videos/temp/{uuid.uuid4()}_{video_filename}"

        try:
            # 上传视频到S3
            print(f"[向量生成] 上传视频到S3: {s3_key}")
            with open(video_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ContentType': 'video/mp4'}
                )

            # 构建S3 URI
            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            print(f"[向量生成] S3 URI: {s3_uri}")

            # 使用异步API调用Nova MME
            model_input = {
                "taskType": "SEGMENTED_EMBEDDING",
                "segmentedEmbeddingParams": {
                    "embeddingPurpose": "GENERIC_INDEX",
                    "embeddingDimension": 1024,
                    "video": {
                        "format": "mp4",
                        "embeddingMode": "AUDIO_VIDEO_COMBINED",
                        "source": {"s3Location": {"uri": s3_uri}},
                        "segmentationConfig": {"durationSeconds": segment_duration}
                    }
                }
            }

            print(f"[向量生成] 启动异步任务...")
            response = self.bedrock.start_async_invoke(
                modelId="amazon.nova-2-multimodal-embeddings-v1:0",
                modelInput=model_input,
                outputDataConfig={
                    "s3OutputDataConfig": {
                        "s3Uri": f"s3://{self.bucket_name}/async-results/"
                    }
                }
            )

            invocation_arn = response['invocationArn']
            print(f"[向量生成] 异步任务已启动: {invocation_arn}")

            # 等待任务完成
            print(f"[向量生成] 等待任务完成...")
            max_wait_time = 1800  # 30分钟
            check_interval = 10   # 每10秒检查一次
            start_time = time.time()

            while time.time() - start_time < max_wait_time:
                status_response = self.bedrock.get_async_invoke(invocationArn=invocation_arn)
                status = status_response['status']

                print(f"[向量生成] 当前状态: {status}")

                if status == 'Completed':
                    print(f"[向量生成] 任务完成，获取结果...")

                    # 获取结果
                    job_id = invocation_arn.split('/')[-1]
                    result_key = f"async-results/{job_id}/segmented-embedding-result.json"

                    result_response = self.s3_client.get_object(
                        Bucket=self.bucket_name,
                        Key=result_key
                    )
                    result_data = json.loads(result_response['Body'].read())

                    # 处理新格式的结果
                    embeddings = []
                    if 'embeddingResults' in result_data:
                        embedding_result = result_data['embeddingResults'][0]
                        if embedding_result['status'] == 'SUCCESS':
                            output_file_uri = embedding_result['outputFileUri']

                            # 解析S3 URI
                            uri_parts = output_file_uri.replace('s3://', '').split('/', 1)
                            bucket = uri_parts[0]
                            key = uri_parts[1]

                            # 读取JSONL文件，添加重试和超时配置
                            print(f"[向量生成] 读取JSONL文件: s3://{bucket}/{key}")

                            max_retries = 3
                            retry_delay = 2

                            for attempt in range(max_retries):
                                try:
                                    # 使用流式读取，避免一次性加载大文件
                                    from botocore.config import Config as BotoConfig

                                    # 创建临时的S3 client，设置更长的超时
                                    s3_temp = boto3.client(
                                        's3',
                                        aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                                        aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                                        region_name=Config.AWS_REGION,
                                        config=BotoConfig(
                                            read_timeout=600,  # 10分钟读取超时
                                            connect_timeout=60,
                                            retries={'max_attempts': 3}
                                        )
                                    )

                                    jsonl_response = s3_temp.get_object(Bucket=bucket, Key=key)

                                    # 流式读取，逐块处理
                                    jsonl_content = b''
                                    for chunk in jsonl_response['Body'].iter_chunks(chunk_size=1024*1024):  # 1MB chunks
                                        jsonl_content += chunk

                                    jsonl_text = jsonl_content.decode('utf-8')
                                    print(f"[向量生成] JSONL文件大小: {len(jsonl_text)} 字符")

                                    # 解析JSONL
                                    line_count = 0
                                    for line in jsonl_text.strip().split('\n'):
                                        if line.strip():
                                            segment_data = json.loads(line)
                                            if 'embedding' in segment_data:
                                                embeddings.append({'embedding': segment_data['embedding']})
                                                line_count += 1

                                    print(f"[向量生成] 解析了 {line_count} 行JSONL数据")
                                    break  # 成功，退出重试循环

                                except Exception as read_error:
                                    print(f"[向量生成] 读取JSONL失败 (尝试 {attempt+1}/{max_retries}): {str(read_error)}")
                                    if attempt < max_retries - 1:
                                        print(f"[向量生成] {retry_delay}秒后重试...")
                                        time.sleep(retry_delay)
                                        retry_delay *= 2  # 指数退避
                                    else:
                                        raise Exception(f"读取JSONL文件失败，已重试{max_retries}次: {str(read_error)}")

                    elif 'embeddings' in result_data:
                        embeddings = result_data['embeddings']

                    print(f"[向量生成] 获取到 {len(embeddings)} 个分段的向量")

                    # 清理S3文件
                    try:
                        self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                        print(f"[向量生成] 已删除临时S3文件: {s3_key}")
                    except Exception as e:
                        print(f"[向量生成] 警告：删除临时S3文件失败: {str(e)}")

                    return embeddings

                elif status == 'Failed':
                    error_msg = status_response.get('failureMessage', 'Unknown error')
                    raise Exception(f"异步任务失败: {error_msg}")

                time.sleep(check_interval)

            raise Exception(f"异步任务超时（{max_wait_time}秒）")

        except Exception as e:
            # 如果出错，尝试清理S3文件
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            except:
                pass
            raise

    def get_embedding(self, content, content_type="text"):
        """
        生成文本或视频的向量嵌入
        """
        try:
            if content_type == "text":
                request = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": 1024,
                        "text": {
                            "truncationMode": "END",
                            "value": content
                        }
                    }
                }
            else:  # video
                with open(content, 'rb') as f:
                    video_base64 = base64.b64encode(f.read()).decode('utf-8')
                request = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": "GENERIC_INDEX",
                        "embeddingDimension": 1024,
                        "video": {
                            "format": "mp4",
                            "embeddingMode": "AUDIO_VIDEO_COMBINED",
                            "source": {"bytes": video_base64}
                        }
                    }
                }

            response = self.bedrock.invoke_model(
                modelId="amazon.nova-2-multimodal-embeddings-v1:0",
                body=json.dumps(request)
            )

            result = json.loads(response['body'].read())
            return result['embeddings'][0]['embedding']

        except Exception as e:
            print(f"Error getting embedding: {str(e)}")
            raise

    def cosine_similarity(self, a, b):
        """计算余弦相似度"""
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def match_clips(self, analysis, clips, threshold=0.05, top_k_per_point=3):
        """
        步骤5: 语义匹配 - 为每个高光要点找Top-K匹配片段

        注意：clips已经包含了embedding，不需要重复生成
        参数：
        - threshold: 最低相似度阈值（降低到0.05以获取更多片段）
        - top_k_per_point: 每个要点选择的最佳片段数（默认3个）
        """
        # 提取要点
        lines = analysis.split('\n')
        points = [line.strip() for line in lines if line.strip() and
                 any(line.strip().startswith(prefix) for prefix in ['A.', 'B.', 'C.', 'D.', 'E.', 'F.', 'G.', 'H.', 'I.', 'J.'])]

        print(f"[匹配] 提取到 {len(points)} 个高光要点")

        # 过滤出有向量的片段
        valid_clips = [c for c in clips if c.get('embedding') is not None]
        print(f"[匹配] 有效片段数: {len(valid_clips)}/{len(clips)}")

        # 为每个要点匹配Top-K片段
        selected_clips = []

        for point in points:
            print(f"[匹配] 处理要点: {point[:80]}...")

            # 获取要点的向量
            text_emb = self.get_embedding(point, "text")

            # 计算与所有片段的相似度
            clip_similarities = []
            for clip in valid_clips:
                video_emb = clip['embedding']
                similarity = self.cosine_similarity(text_emb, video_emb)

                if similarity > threshold:
                    clip_copy = clip.copy()
                    clip_copy['similarity'] = similarity
                    clip_copy['point'] = point
                    clip_similarities.append((similarity, clip_copy))

            # 按相似度排序，选择Top-K
            clip_similarities.sort(key=lambda x: x[0], reverse=True)
            top_clips = clip_similarities[:top_k_per_point]

            if top_clips:
                for sim, clip in top_clips:
                    selected_clips.append(clip)
                    print(f"[匹配]   ✓ 选中片段 {clip['index']} (时间: {clip['timestamp']}s, 相似度: {sim:.3f})")
            else:
                print(f"[匹配]   ✗ 未找到匹配片段 (阈值: {threshold})")

        # 按时间顺序排序并去重
        selected_clips.sort(key=lambda x: x['timestamp'])

        # 第一步：去除完全相同的片段（根据index）
        seen_indices = set()
        unique_clips = []
        for clip in selected_clips:
            if clip['index'] not in seen_indices:
                unique_clips.append(clip)
                seen_indices.add(clip['index'])
            else:
                print(f"[匹配] 跳过重复片段: index={clip['index']}, 时间={clip['timestamp']}s")

        # 第二步：去除时间上重叠的片段（保留相似度更高的）
        filtered_clips = []
        for clip in unique_clips:
            # 检查是否与已选片段重叠
            overlap = False
            for selected in filtered_clips:
                if abs(clip['timestamp'] - selected['timestamp']) < 3:  # 3秒内视为重叠
                    overlap = True
                    # 如果当前片段相似度更高，替换
                    if clip['similarity'] > selected['similarity']:
                        print(f"[匹配] 替换重叠片段: {selected['index']}(相似度{selected['similarity']:.3f}) -> {clip['index']}(相似度{clip['similarity']:.3f})")
                        filtered_clips.remove(selected)
                        filtered_clips.append(clip)
                    break

            if not overlap:
                filtered_clips.append(clip)

        filtered_clips.sort(key=lambda x: x['timestamp'])
        print(f"[匹配] 选中 {len(filtered_clips)} 个片段（去重后），开始提取实际视频文件...")

        # 现在才使用FFmpeg提取选中的clip
        for i, clip in enumerate(filtered_clips):
            if clip['path'] is None:  # 如果还没有实际文件
                clip_path = os.path.join(clip['output_dir'], f'clip_{clip["index"]:04d}.mp4')

                print(f"[匹配] 提取片段 {i+1}/{len(filtered_clips)}: 时间={clip['timestamp']}s...")

                extract_cmd = [
                    'ffmpeg', '-ss', str(clip['timestamp']),
                    '-i', clip['video_source'],
                    '-t', str(clip['duration']),
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-g', '30',  # 强制每30帧一个关键帧
                    '-y', clip_path
                ]
                subprocess.run(extract_cmd, check=True, capture_output=True)
                clip['path'] = clip_path

        print(f"[匹配] 所有片段提取完成")
        return filtered_clips

    def create_highlight_video(self, selected_clips, output_path, transition_duration=0.5):
        """
        步骤6: 使用FFmpeg拼接高光片段，使用简单的concat + 淡入淡出

        transition_duration: 转场时长（秒），默认0.5秒
        """
        try:
            if len(selected_clips) == 0:
                raise Exception("没有选中的片段可以拼接")

            if len(selected_clips) == 1:
                # 只有一个片段，直接复制
                print(f"[拼接] 只有1个片段，直接复制")
                import shutil
                shutil.copy2(selected_clips[0]['path'], output_path)
                return output_path

            print(f"[拼接] 开始拼接 {len(selected_clips)} 个片段，使用concat方法...")

            # 方法：先为每个片段添加淡入淡出，然后使用concat拼接
            temp_dir = os.path.dirname(selected_clips[0]['path'])
            faded_clips = []

            # 第一步：为每个片段添加淡入淡出效果
            for i, clip in enumerate(selected_clips):
                faded_path = os.path.join(temp_dir, f'faded_{i:04d}.mp4')
                duration = self.get_video_duration(clip['path'])

                fade_filters = []

                if i == 0:
                    # 第一个片段：只有开头淡入
                    fade_filters.append(f"fade=t=in:st=0:d={transition_duration}")
                elif i == len(selected_clips) - 1:
                    # 最后一个片段：只有结尾淡出
                    fade_out_start = max(0, duration - transition_duration)
                    fade_filters.append(f"fade=t=out:st={fade_out_start}:d={transition_duration}")
                else:
                    # 中间片段：既有淡入也有淡出
                    fade_out_start = max(0, duration - transition_duration)
                    fade_filters.append(f"fade=t=in:st=0:d={transition_duration},fade=t=out:st={fade_out_start}:d={transition_duration}")

                video_filter = ",".join(fade_filters)

                # 音频淡入淡出
                audio_filters = []
                if i == 0:
                    audio_filters.append(f"afade=t=in:st=0:d={transition_duration}")
                elif i == len(selected_clips) - 1:
                    fade_out_start = max(0, duration - transition_duration)
                    audio_filters.append(f"afade=t=out:st={fade_out_start}:d={transition_duration}")
                else:
                    fade_out_start = max(0, duration - transition_duration)
                    audio_filters.append(f"afade=t=in:st=0:d={transition_duration},afade=t=out:st={fade_out_start}:d={transition_duration}")

                audio_filter = ",".join(audio_filters)

                print(f"[拼接] 处理片段{i}: 添加淡入淡出...")

                fade_cmd = [
                    'ffmpeg', '-i', clip['path'],
                    '-vf', video_filter,
                    '-af', audio_filter,
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-y', faded_path
                ]

                subprocess.run(fade_cmd, check=True, capture_output=True)
                faded_clips.append(faded_path)

            # 第二步：使用concat filter拼接所有片段
            print(f"[拼接] 使用concat拼接 {len(faded_clips)} 个处理后的片段...")

            # 构建filter_complex
            inputs = "".join([f"[{i}:v][{i}:a]" for i in range(len(faded_clips))])
            concat_filter = f"{inputs}concat=n={len(faded_clips)}:v=1:a=1[vout][aout]"

            ffmpeg_cmd = ['ffmpeg']
            for faded_clip in faded_clips:
                ffmpeg_cmd.extend(['-i', faded_clip])

            ffmpeg_cmd.extend([
                '-filter_complex', concat_filter,
                '-map', '[vout]',
                '-map', '[aout]',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                '-y', output_path
            ])

            result = subprocess.run(
                ffmpeg_cmd,
                check=True,
                capture_output=True,
                text=True
            )

            print(f"[拼接] 高光视频生成完成: {output_path}")

            # 清理临时淡入淡出片段
            for faded_clip in faded_clips:
                try:
                    os.remove(faded_clip)
                except:
                    pass

            # 检查输出文件
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"[拼接] 输出文件大小: {output_size:.2f}MB")

            return output_path

        except subprocess.CalledProcessError as e:
            print(f"[拼接] FFmpeg错误: {e.stderr}")
            raise Exception(f"视频拼接失败: {e.stderr}")
        except Exception as e:
            print(f"[拼接] 错误: {str(e)}")
            raise

    def get_video_duration(self, video_path):
        """获取视频时长"""
        try:
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            duration = float(subprocess.check_output(probe_cmd).decode().strip())
            return duration
        except:
            return 0
