import os
import json
import base64
import subprocess
from pathlib import Path
from config import Config
import google.generativeai as genai

class GeminiAnalyzer:
    """
    Google Gemini视频分析器
    支持Gemini 2.5和Gemini 2.5 Pro
    """

    def __init__(self):
        # 从环境变量获取API密钥
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        genai.configure(api_key=api_key)

        # 支持的模型
        self.models = {
            'gemini-2.5-flash': 'gemini-2.0-flash-exp',  # Gemini 2.5 Flash
            'gemini-2.5-pro': 'gemini-exp-1206'  # Gemini 2.5 Pro
        }

    def generate_summary_and_criteria(self, video_path, model_name='gemini-2.5-flash'):
        """
        使用Gemini分析视频，生成总结和高光标准

        Args:
            video_path: 视频文件路径
            model_name: 模型名称 ('gemini-2.5-flash' 或 'gemini-2.5-pro')

        Returns:
            (analysis_text, video_path): 分析结果和视频路径
        """
        try:
            # 获取视频信息
            file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
            duration = self.get_video_duration(video_path)

            print(f"[Gemini-{model_name}] 视频大小: {file_size:.2f}MB, 时长: {duration:.2f}秒")

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

            # 上传视频文件
            print(f"[Gemini-{model_name}] 上传视频文件...")
            video_file = genai.upload_file(compressed_path)
            print(f"[Gemini-{model_name}] 视频上传完成: {video_file.name}")

            # 等待视频处理完成
            import time
            while video_file.state.name == "PROCESSING":
                print(f"[Gemini-{model_name}] 等待视频处理...")
                time.sleep(2)
                video_file = genapi.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                raise Exception(f"视频处理失败: {video_file.state.name}")

            # 调用Gemini模型
            model_id = self.models.get(model_name, self.models['gemini-2.5-flash'])
            print(f"[Gemini-{model_name}] 使用模型: {model_id}")

            model = genai.GenerativeModel(model_id)

            print(f"[Gemini-{model_name}] 开始分析...")
            response = model.generate_content(
                [video_file, prompt],
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 2000,
                }
            )

            analysis = response.text

            print(f"[Gemini-{model_name}] 分析完成，长度: {len(analysis)} 字符")

            # 清理上传的文件
            try:
                genai.delete_file(video_file.name)
                print(f"[Gemini-{model_name}] 已清理临时文件")
            except:
                pass

            return analysis, compressed_path

        except Exception as e:
            print(f"[Gemini-{model_name}] 错误: {str(e)}")
            raise

    def identify_highlight_moments(self, video_path, criteria, model_name='gemini-2.5-flash'):
        """
        使用Gemini根据标准识别高光时刻并定位时间戳

        Args:
            video_path: 视频文件路径
            criteria: 高光判定标准
            model_name: 模型名称

        Returns:
            JSON格式的高光数据
        """
        try:
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            video_duration = self.get_video_duration(video_path)

            print(f"[Gemini-{model_name}] 开始识别高光时刻...")

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

            # 上传视频文件
            print(f"[Gemini-{model_name}] 上传视频文件...")
            video_file = genai.upload_file(video_path)

            # 等待视频处理完成
            import time
            while video_file.state.name == "PROCESSING":
                print(f"[Gemini-{model_name}] 等待视频处理...")
                time.sleep(2)
                video_file = genai.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                raise Exception(f"视频处理失败")

            # 调用Gemini模型
            model_id = self.models.get(model_name, self.models['gemini-2.5-flash'])
            model = genai.GenerativeModel(model_id)

            print(f"[Gemini-{model_name}] 开始识别...")
            response = model.generate_content(
                [video_file, prompt],
                generation_config={
                    'temperature': 0.4,
                    'max_output_tokens': 3000,
                }
            )

            response_text = response.text
            print(f"[Gemini-{model_name}] AI返回: {response_text[:500]}...")

            # 提取JSON
            highlights_data = self._extract_json(response_text)

            # 验证和清理数据
            highlights_data = self._validate_highlights(highlights_data, video_duration)

            print(f"[Gemini-{model_name}] 识别到 {len(highlights_data['highlights'])} 个高光片段")

            # 清理上传的文件
            try:
                genai.delete_file(video_file.name)
            except:
                pass

            return highlights_data

        except Exception as e:
            print(f"[Gemini-{model_name}] 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def _compress_if_needed(self, video_path):
        """智能压缩视频（Gemini限制100MB）"""
        file_size = os.path.getsize(video_path) / (1024 * 1024)

        if file_size <= 100:
            return video_path

        # 需要压缩
        output_path = video_path.replace('.mp4', '_compressed_gemini.mp4')
        duration = self.get_video_duration(video_path)
        target_bitrate = int((95 * 8 * 1024) / duration) - 128  # 压缩到95MB

        print(f"[Gemini压缩] 压缩到95MB，目标比特率: {target_bitrate}kbps")

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

    def _extract_json(self, text):
        """从文本中提取JSON"""
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
