import boto3
import json
import base64
import subprocess
import os
import uuid
from pathlib import Path
from config import Config

class DirectHighlightExtractor:
    """
    直接时间定位模式的高光提取器
    使用Nova Pro直接分析视频并返回时间戳，不使用embedding匹配
    """
    def __init__(self):
        from botocore.config import Config as BotoConfig
        self.bedrock = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION,
            config=BotoConfig(
                read_timeout=300,  # 5分钟读取超时
                connect_timeout=60,
                retries={'max_attempts': 3}
            )
        )
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )
        self.bucket_name = Config.S3_BUCKET

    def generate_summary_and_criteria(self, video_path):
        """
        步骤1: 使用Nova Pro分析视频，生成总结和高光标准
        """
        try:
            # 获取视频信息
            file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
            duration = self.get_video_duration(video_path)

            print(f"[直接定位-步骤1] 视频大小: {file_size:.2f}MB, 时长: {duration:.2f}秒")

            # 先压缩视频（如果需要）
            compressed_path = self._compress_if_needed(video_path)

            prompt = """请分析这个视频并完成以下任务：

### Task 1: 视频总结
简要描述视频的整体内容、主题和风格（2-3句话）。

### Task 2: 高光判定标准
根据视频内容，制定适合该视频的高光片段判定标准。请按以下格式输出：

## 高光片段判定标准：
- [标准1]
- [标准2]
- [标准3]
- [标准4]
- [标准5]

**标准制定角度：**
- Visual dynamics: 画面动态、运动强度、视觉效果
- Emotional impact: 情感冲击、戏剧张力、兴奋程度
- Technical complexity: 技术难度、技巧性、协调性
- Narrative significance: 故事转折点、关键时刻
- Audience appeal: 传播性、记忆点、吸引力

请确保标准具体且可执行，便于后续识别高光片段。"""

            # 调用Nova Pro
            if file_size < 25:
                print(f"[直接定位-步骤1] 使用inline base64分析")
                with open(compressed_path, 'rb') as f:
                    video_base64 = base64.b64encode(f.read()).decode('utf-8')

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
            else:
                print(f"[直接定位-步骤1] 使用S3 URI分析")
                response = self._analyze_via_s3(compressed_path, prompt)

            result = json.loads(response['body'].read())
            analysis = result['output']['message']['content'][0]['text']

            print(f"[直接定位-步骤1] 分析完成，长度: {len(analysis)} 字符")
            return analysis, compressed_path

        except Exception as e:
            print(f"[直接定位-步骤1] 错误: {str(e)}")
            raise

    def identify_highlight_moments(self, video_path, criteria, allow_edit=True):
        """
        步骤2: 使用Nova Pro根据标准识别高光时刻并定位时间戳

        返回JSON格式：
        {
            "highlights": [
                {
                    "index": 1,
                    "start_time": 12.5,
                    "end_time": 18.3,
                    "duration": 5.8,
                    "description": "精彩的跳跃动作",
                    "intensity": "high",
                    "reason": "动作精彩、技巧性强"
                }
            ]
        }
        """
        try:
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            video_duration = self.get_video_duration(video_path)

            print(f"[直接定位-步骤2] 开始识别高光时刻...")

            prompt = f"""请根据以下高光判定标准，分析视频并精确定位所有高光片段。

{criteria}

### Task:
You are an expert in video content analysis and temporal localization.

### Analysis Process (Follow these steps):
Step 1: Watch the entire video and identify all highlight moments
Step 2: For each moment, determine precise start and end timestamps
Step 3: Verify all timestamps are within the video duration ({video_duration:.2f} seconds)
Step 4: Output structured JSON format only

### Output Format (JSON only, no other text):
```json
{{
    "highlights": [
        {{
            "index": 1,
            "start_time": 12.5,
            "end_time": 18.3,
            "duration": 5.8,
            "description": "具体描述这个高光片段的内容",
            "intensity": "high",
            "reason": "符合哪条判定标准"
        }}
    ]
}}
```

**重要要求：**
1. 时间戳必须精确到小数点后1位（秒）
2. start_time 必须 < end_time
3. 所有时间戳必须在 0 到 {video_duration:.2f} 秒之间
4. 每个高光片段建议时长：3-10秒
5. intensity可选值: "high", "medium", "low"
6. 只输出JSON，不要有其他解释文字
7. 按时间顺序排列高光片段"""

            # 调用Nova Pro
            if file_size < 25:
                print(f"[直接定位-步骤2] 使用inline base64分析")
                with open(video_path, 'rb') as f:
                    video_base64 = base64.b64encode(f.read()).decode('utf-8')

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
                            "max_new_tokens": 3000
                        }
                    })
                )
                result = json.loads(response['body'].read())
            else:
                print(f"[直接定位-步骤2] 使用S3 URI分析")
                response = self._analyze_via_s3(video_path, prompt)
                result = json.loads(response['body'].read())

            response_text = result['output']['message']['content'][0]['text']
            print(f"[直接定位-步骤2] AI返回: {response_text[:500]}...")

            # 提取JSON（处理可能的markdown包裹）
            highlights_data = self._extract_json(response_text)

            # 验证和清理数据
            highlights_data = self._validate_highlights(highlights_data, video_duration)

            print(f"[直接定位-步骤2] 识别到 {len(highlights_data['highlights'])} 个高光片段")

            return highlights_data

        except Exception as e:
            print(f"[直接定位-步骤2] 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def extract_and_stitch_clips(self, video_path, highlights_data, output_path, transition_duration=0.5):
        """
        步骤3: 根据时间戳提取片段并拼接，包含去重和过渡
        """
        try:
            highlights = highlights_data['highlights']

            if len(highlights) == 0:
                raise Exception("没有高光片段可以提取")

            print(f"[直接定位-步骤3] 开始提取 {len(highlights)} 个高光片段...")

            # 去重：移除重叠的片段
            highlights = self._deduplicate_highlights(highlights)
            print(f"[直接定位-步骤3] 去重后剩余 {len(highlights)} 个片段")

            # 创建临时目录
            temp_dir = os.path.join('static', 'clips', str(uuid.uuid4()))
            os.makedirs(temp_dir, exist_ok=True)

            # 提取每个片段
            clip_paths = []
            for i, highlight in enumerate(highlights):
                clip_path = os.path.join(temp_dir, f'clip_{i:04d}.mp4')

                print(f"[直接定位-步骤3] 提取片段 {i+1}/{len(highlights)}: {highlight['start_time']:.1f}s - {highlight['end_time']:.1f}s")

                extract_cmd = [
                    'ffmpeg', '-ss', str(highlight['start_time']),
                    '-i', video_path,
                    '-to', str(highlight['end_time'] - highlight['start_time']),
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-g', '30',  # 关键帧对齐
                    '-y', clip_path
                ]

                subprocess.run(extract_cmd, check=True, capture_output=True)
                clip_paths.append({
                    'path': clip_path,
                    'highlight': highlight
                })

            # 拼接片段（使用相同的两步法：先淡入淡出，再concat）
            print(f"[直接定位-步骤3] 开始拼接片段...")

            if len(clip_paths) == 1:
                # 只有一个片段，直接复制
                import shutil
                shutil.copy2(clip_paths[0]['path'], output_path)
            else:
                # 多个片段，添加过渡效果
                self._stitch_with_transitions(clip_paths, output_path, transition_duration)

            # 清理临时文件
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass

            print(f"[直接定位-步骤3] 高光视频生成完成: {output_path}")
            return output_path, highlights

        except Exception as e:
            print(f"[直接定位-步骤3] 错误: {str(e)}")
            raise

    def _compress_if_needed(self, video_path):
        """智能压缩视频"""
        file_size = os.path.getsize(video_path) / (1024 * 1024)

        if file_size <= 25:
            return video_path

        if file_size <= 100:
            return video_path

        # 需要压缩
        output_path = video_path.replace('.mp4', '_compressed.mp4')
        duration = self.get_video_duration(video_path)
        target_bitrate = int((100 * 8 * 1024) / duration) - 128

        print(f"[压缩] 压缩到100MB，目标比特率: {target_bitrate}kbps")

        compress_cmd = [
            'ffmpeg', '-i', video_path,
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

        subprocess.run(compress_cmd, check=True, capture_output=True)
        return output_path

    def _analyze_via_s3(self, video_path, prompt):
        """使用S3 URI分析视频"""
        video_filename = os.path.basename(video_path)
        s3_key = f"videos/temp/{uuid.uuid4()}_{video_filename}"

        try:
            print(f"[S3] 上传视频到S3: {s3_key}")
            with open(video_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ContentType': 'video/mp4'}
                )

            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            print(f"[S3] S3 URI: {s3_uri}")

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
                        "max_new_tokens": 3000
                    }
                })
            )

            # 删除临时文件
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                print(f"[S3] 已删除临时文件: {s3_key}")
            except Exception as e:
                print(f"[S3] 警告：删除临时文件失败: {str(e)}")

            return response

        except Exception as e:
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            except:
                pass
            raise

    def _extract_json(self, text):
        """从文本中提取JSON（处理markdown包裹）"""
        import re

        # 尝试提取 ```json ... ``` 之间的内容
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # 尝试提取 { ... }
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            else:
                json_text = text

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"[JSON解析错误] 原始文本: {text[:500]}")
            raise Exception(f"无法解析JSON: {str(e)}")

    def _validate_highlights(self, highlights_data, video_duration):
        """验证和清理高光数据"""
        if 'highlights' not in highlights_data:
            raise Exception("返回的JSON中没有'highlights'字段")

        valid_highlights = []

        for h in highlights_data['highlights']:
            # 验证必需字段
            if 'start_time' not in h or 'end_time' not in h:
                print(f"[验证] 跳过缺少时间戳的片段: {h}")
                continue

            start = float(h['start_time'])
            end = float(h['end_time'])

            # 验证时间范围
            if start < 0 or end > video_duration or start >= end:
                print(f"[验证] 跳过无效时间戳: {start:.1f}s - {end:.1f}s (视频时长: {video_duration:.1f}s)")
                continue

            # 补充缺失字段
            h['duration'] = round(end - start, 1)
            h['description'] = h.get('description', '高光片段')
            h['intensity'] = h.get('intensity', 'medium')
            h['reason'] = h.get('reason', '')

            valid_highlights.append(h)

        if len(valid_highlights) == 0:
            raise Exception("没有有效的高光片段")

        # 按时间排序
        valid_highlights.sort(key=lambda x: x['start_time'])

        # 重新编号
        for i, h in enumerate(valid_highlights):
            h['index'] = i + 1

        return {'highlights': valid_highlights}

    def _deduplicate_highlights(self, highlights):
        """去重：移除重叠的片段，保留强度更高的"""
        if len(highlights) <= 1:
            return highlights

        # 按强度排序（high > medium > low）
        intensity_order = {'high': 3, 'medium': 2, 'low': 1}
        highlights_sorted = sorted(highlights, key=lambda x: intensity_order.get(x.get('intensity', 'medium'), 2), reverse=True)

        filtered = []

        for highlight in highlights_sorted:
            overlap = False

            for selected in filtered:
                # 检查是否重叠
                if not (highlight['end_time'] <= selected['start_time'] or highlight['start_time'] >= selected['end_time']):
                    overlap = True
                    print(f"[去重] 片段重叠，保留强度更高的: {selected['start_time']:.1f}s-{selected['end_time']:.1f}s")
                    break

            if not overlap:
                filtered.append(highlight)

        # 按时间排序
        filtered.sort(key=lambda x: x['start_time'])

        return filtered

    def _stitch_with_transitions(self, clip_paths, output_path, transition_duration=0.5):
        """使用两步法拼接：先添加淡入淡出，再concat"""
        temp_dir = os.path.dirname(clip_paths[0]['path'])
        faded_clips = []

        # 第一步：为每个片段添加淡入淡出
        for i, clip_data in enumerate(clip_paths):
            faded_path = os.path.join(temp_dir, f'faded_{i:04d}.mp4')
            duration = self.get_video_duration(clip_data['path'])

            fade_filters = []
            audio_filters = []

            if i == 0:
                # 第一个片段：只淡入
                fade_filters.append(f"fade=t=in:st=0:d={transition_duration}")
                audio_filters.append(f"afade=t=in:st=0:d={transition_duration}")
            elif i == len(clip_paths) - 1:
                # 最后一个片段：只淡出
                fade_out_start = max(0, duration - transition_duration)
                fade_filters.append(f"fade=t=out:st={fade_out_start}:d={transition_duration}")
                audio_filters.append(f"afade=t=out:st={fade_out_start}:d={transition_duration}")
            else:
                # 中间片段：淡入淡出
                fade_out_start = max(0, duration - transition_duration)
                fade_filters.append(f"fade=t=in:st=0:d={transition_duration},fade=t=out:st={fade_out_start}:d={transition_duration}")
                audio_filters.append(f"afade=t=in:st=0:d={transition_duration},afade=t=out:st={fade_out_start}:d={transition_duration}")

            fade_cmd = [
                'ffmpeg', '-i', clip_data['path'],
                '-vf', ','.join(fade_filters),
                '-af', ','.join(audio_filters),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-y', faded_path
            ]

            subprocess.run(fade_cmd, check=True, capture_output=True)
            faded_clips.append(faded_path)

        # 第二步：concat拼接
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

        subprocess.run(ffmpeg_cmd, check=True, capture_output=True)

        # 清理临时文件
        for faded_clip in faded_clips:
            try:
                os.remove(faded_clip)
            except:
                pass

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
