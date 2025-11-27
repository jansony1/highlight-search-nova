from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
import os
import uuid
import threading
from werkzeug.utils import secure_filename
from config import Config
from utils.s3_handler import S3Handler
from utils.embedding import NovaEmbedding
from utils.async_embedding import AsyncNovaEmbedding
from utils.s3_vector_search import S3VectorSearch
from utils.highlight_extractor import HighlightExtractor

app = Flask(__name__)
app.config.from_object(Config)

# 设置最大上传文件大小为500MB
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

s3_handler = S3Handler()
nova_embedding = NovaEmbedding()
async_embedding = AsyncNovaEmbedding()

# 使用S3 Vectors进行向量搜索
vector_search = S3VectorSearch()

# 高光视频提取器
highlight_extractor = HighlightExtractor()

# 存储异步任务状态
async_jobs = {}

# 存储高光提取任务状态
highlight_jobs = {}

def allowed_file(filename, file_type):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS'][file_type]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        file_type = request.form.get('type')
        text_input = request.form.get('text', '')
        embedding_dimension = int(request.form.get('embedding_dimension', 1024))
        
        print(f"Debug: filename={file.filename}, file_type={file_type}, embedding_dimension={embedding_dimension}")
        print(f"Debug: allowed extensions for {file_type}: {app.config['ALLOWED_EXTENSIONS'].get(file_type, 'NOT FOUND')}")
        
        # 验证embedding维度
        valid_dimensions = [256, 384, 1024, 3072]
        if embedding_dimension not in valid_dimensions:
            return jsonify({'error': f'Invalid embedding dimension. Must be one of: {valid_dimensions}'}), 400
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, file_type):
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'no extension'
            return jsonify({'error': f'File type not allowed. Got: {file_ext}, Expected: {app.config["ALLOWED_EXTENSIONS"].get(file_type, [])}'}), 400
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        file_key = f"{file_type}/{file_id}_{filename}"
        
        print(f"Debug: Processing file {filename} as {file_type} with {embedding_dimension}D embeddings")
        
        # Save locally for processing first
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(local_path)
        print(f"Debug: File saved locally to {local_path}")
        
        # Upload to S3
        try:
            with open(local_path, 'rb') as f:
                s3_url = s3_handler.upload_file(f, file_key)
            print(f"Debug: File uploaded to S3: {s3_url}")
        except Exception as e:
            print(f"Debug: S3 upload failed: {str(e)}")
            # Continue without S3 for now
            s3_url = f"local://{local_path}"
        
        # Generate embedding
        try:
            if file_type == 'text':
                with open(local_path, 'r') as f:
                    content = f.read()
                embedding = nova_embedding.generate_embedding('text', content, dimension=embedding_dimension)
                print(f"Debug: Embedding generated successfully, length: {len(embedding)}")
                
                # 验证embedding有效性
                if embedding and len(embedding) > 0 and any(x != 0 for x in embedding):
                    # Store vector immediately for text
                    metadata = {
                        'filename': filename,
                        'file_type': file_type,
                        's3_url': s3_url,
                        'text': text_input
                    }
                    try:
                        vector_search.add_vector(file_id, embedding, metadata)
                        print(f"Debug: Vector stored successfully for {file_id}")
                    except Exception as storage_error:
                        print(f"Debug: Vector storage failed for {file_id}: {str(storage_error)}")
                        raise Exception(f"Vector storage failed: {str(storage_error)}")
                else:
                    raise Exception("Generated embedding is empty or all zeros")
                
            elif file_type == 'image':
                encoded_content = nova_embedding.encode_image(local_path)
                embedding = nova_embedding.generate_embedding('image', encoded_content, text_input, dimension=embedding_dimension)
                print(f"Debug: Embedding generated successfully, length: {len(embedding)}")
                
                # 验证embedding有效性
                if embedding and len(embedding) > 0 and any(x != 0 for x in embedding):
                    # Store vector immediately for image
                    metadata = {
                        'filename': filename,
                        'file_type': file_type,
                        's3_url': s3_url,
                        'text': text_input
                    }
                    try:
                        vector_search.add_vector(file_id, embedding, metadata)
                        print(f"Debug: Vector stored successfully for {file_id}")
                    except Exception as storage_error:
                        print(f"Debug: Vector storage failed for {file_id}: {str(storage_error)}")
                        raise Exception(f"Vector storage failed: {str(storage_error)}")
                else:
                    raise Exception("Generated embedding is empty or all zeros")
                
            elif file_type in ['video', 'audio']:
                print(f"Debug: {file_type} file detected, using async API by default...")
                
                # 启动异步处理
                invocation_arn = async_embedding.start_async_embedding(
                    file_type, s3_url, text_input, dimension=embedding_dimension
                )
                
                # 存储异步任务信息
                async_jobs[file_id] = {
                    'invocation_arn': invocation_arn,
                    'filename': filename,
                    'file_type': file_type,
                    's3_url': s3_url,
                    'text': text_input,
                    'status': 'processing'
                }
                
                # 启动后台线程处理异步结果
                def process_async_result():
                    try:
                        print(f"Debug: Starting background processing for {file_id}")
                        result = async_embedding.wait_for_completion(invocation_arn)
                        
                        # 处理分段结果，合并为单个embedding
                        if result and 'embeddings' in result:
                            embeddings = result['embeddings']
                            if embeddings and len(embeddings) > 0:
                                # 验证embedding数据有效性
                                valid_embeddings = []
                                for emb in embeddings:
                                    if 'embedding' in emb and emb['embedding'] and len(emb['embedding']) > 0:
                                        # 检查embedding不全为0
                                        if any(x != 0 for x in emb['embedding']):
                                            valid_embeddings.append(emb['embedding'])
                                
                                if valid_embeddings:
                                    import numpy as np
                                    combined_embedding = np.mean(valid_embeddings, axis=0).tolist()
                                    
                                    # 再次验证合并后的embedding
                                    if len(combined_embedding) > 0 and any(x != 0 for x in combined_embedding):
                                        # 存储向量
                                        metadata = {
                                            'filename': filename,
                                            'file_type': file_type,
                                            's3_url': s3_url,
                                            'text': text_input,
                                            'async_processed': True,
                                            'segments': len(valid_embeddings)
                                        }
                                        
                                        try:
                                            vector_search.add_vector(file_id, combined_embedding, metadata)
                                            async_jobs[file_id]['status'] = 'completed'
                                            async_jobs[file_id]['segments'] = len(valid_embeddings)
                                            print(f"Debug: Async processing completed for {file_id} with {len(valid_embeddings)} valid segments")
                                        except Exception as storage_error:
                                            async_jobs[file_id]['status'] = 'failed'
                                            async_jobs[file_id]['error'] = f'Vector storage failed: {str(storage_error)}'
                                            print(f"Debug: Vector storage failed for {file_id}: {str(storage_error)}")
                                    else:
                                        async_jobs[file_id]['status'] = 'failed'
                                        async_jobs[file_id]['error'] = 'Generated embedding is empty or all zeros'
                                        print(f"Debug: Generated embedding is invalid for {file_id}")
                                else:
                                    async_jobs[file_id]['status'] = 'failed'
                                    async_jobs[file_id]['error'] = 'No valid embeddings found in segments'
                                    print(f"Debug: No valid embeddings found for {file_id}")
                            else:
                                async_jobs[file_id]['status'] = 'failed'
                                async_jobs[file_id]['error'] = 'No embeddings in result'
                                print(f"Debug: No embeddings in result for {file_id}")
                        else:
                            async_jobs[file_id]['status'] = 'failed'
                            async_jobs[file_id]['error'] = 'Invalid result format - no embeddings key found'
                            print(f"Debug: Invalid result format for {file_id}: {result.keys() if result else 'None'}")
                            
                    except Exception as e:
                        async_jobs[file_id]['status'] = 'failed'
                        async_jobs[file_id]['error'] = str(e)
                        print(f"Debug: Async processing failed for {file_id}: {str(e)}")
                
                thread = threading.Thread(target=process_async_result)
                thread.daemon = True
                thread.start()
                
                # 返回异步处理状态
                return jsonify({
                    'success': True,
                    'file_id': file_id,
                    'message': f'{file_type}文件已上传到S3，正在后台异步处理embedding...',
                    'async_processing': True,
                    'invocation_arn': invocation_arn
                })
            else:
                raise Exception(f"Unsupported file type: {file_type}")
                
        except Exception as e:
            print(f"Debug: Embedding generation failed: {str(e)}")
            raise Exception(f"Embedding generation failed: {str(e)}")
        
        # Clean up local file
        try:
            os.remove(local_path)
            print(f"Debug: Local file cleaned up")
        except Exception as e:
            print(f"Debug: File cleanup failed: {str(e)}")
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'message': 'File uploaded and processed successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search():
    try:
        print("Debug: [STEP 1] Search API called")
        
        data = request.get_json()
        query_text = data.get('query', '')
        top_k = data.get('top_k', 5)
        search_dimension = data.get('search_dimension', None)  # 新增：搜索维度参数
        
        print(f"Debug: [STEP 2] Request parsed - query: '{query_text}', top_k: {top_k}, search_dimension: {search_dimension}")
        
        if not query_text.strip():
            print("Debug: [STEP 3] Empty query validation failed")
            return jsonify({'error': 'Query text is required'}), 400
        
        print("Debug: [STEP 3] Query validation passed")
        
        # 确定使用的维度
        if search_dimension is not None:
            # 用户指定了维度
            if search_dimension not in [256, 384, 1024, 3072]:
                return jsonify({'error': f'Invalid search dimension: {search_dimension}'}), 400
            query_dimension = search_dimension
            print(f"Debug: [STEP 4] Using user-specified dimension: {query_dimension}")
        else:
            # 自动检测维度
            query_dimension = vector_search.detect_vector_dimension()
            print(f"Debug: [STEP 4] Auto-detected dimension: {query_dimension}")
        
        # Generate query embedding with specified dimension
        print("Debug: [STEP 5] Starting query embedding generation...")
        try:
            print(f"Debug: [STEP 5.1] Generating {query_dimension}D query embedding...")
            query_embedding = nova_embedding.generate_embedding('text', query_text.strip(), dimension=query_dimension)
            print(f"Debug: [STEP 5.2] Query embedding completed, length: {len(query_embedding)}")
        except Exception as e:
            print(f"Debug: [STEP 5.ERROR] Query embedding failed: {str(e)}")
            return jsonify({'error': f'Failed to generate query embedding: {str(e)}'}), 500
        
        # Search similar vectors with dimension constraint
        print("Debug: [STEP 6] Starting vector search...")
        try:
            print(f"Debug: [STEP 6.1] Searching with S3 Vectors...")
            results = vector_search.search(query_embedding, top_k)
            print(f"Debug: [STEP 6.2] Vector search completed, found {len(results)} results")
        except Exception as e:
            print(f"Debug: [STEP 6.ERROR] Vector search failed: {str(e)}")
            return jsonify({'error': f'Vector search failed: {str(e)}'}), 500
        
        print("Debug: [STEP 7] Preparing response...")
        response_data = {
            'success': True,
            'results': results,
            'search_dimension': query_dimension  # 返回实际使用的维度
        }
        print("Debug: [STEP 8] Returning response")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Debug: [STEP ERROR] Search API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/async-status/<file_id>', methods=['GET'])
def get_async_status(file_id):
    try:
        if file_id not in async_jobs:
            return jsonify({'error': 'Async job not found'}), 404
        
        job_info = async_jobs[file_id]
        
        # 如果还在处理中，检查最新状态
        if job_info['status'] == 'processing':
            try:
                status_info = async_embedding.check_async_status(job_info['invocation_arn'])
                bedrock_status = status_info['status']
                
                if bedrock_status == 'Failed':
                    job_info['status'] = 'failed'
                    job_info['error'] = status_info['response'].get('failureMessage', 'Unknown error')
                elif bedrock_status == 'Completed':
                    # 状态会由后台线程更新，这里只是同步一下
                    pass
                    
            except Exception as e:
                print(f"Debug: Error checking async status: {str(e)}")
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'status': job_info['status'],
            'filename': job_info['filename'],
            'file_type': job_info['file_type'],
            'error': job_info.get('error'),
            'segments': job_info.get('segments')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/results')
def results():
    return render_template('results.html')

@app.route('/highlight')
def highlight():
    """高光视频提取页面"""
    return render_template('highlight.html')

@app.route('/api/extract-highlight', methods=['POST'])
def extract_highlight():
    """开始高光视频提取流程"""
    try:
        print(f"\n[API] 收到高光提取请求")

        # 获取参数
        theme = request.form.get('theme', '').strip()
        print(f"[API] 主题: {theme}")

        if not theme:
            return jsonify({'error': '请输入高光主题'}), 400

        if 'video' not in request.files:
            return jsonify({'error': '请上传视频文件'}), 400

        video_file = request.files['video']
        if video_file.filename == '':
            return jsonify({'error': '未选择视频文件'}), 400

        # 验证文件类型
        allowed_extensions = {'mp4', 'avi', 'mov', 'wmv', 'mkv', 'flv'}
        filename = secure_filename(video_file.filename)
        if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return jsonify({'error': f'不支持的文件格式。请上传视频文件（支持：{", ".join(allowed_extensions)}）'}), 400

        # 保存视频文件
        job_id = str(uuid.uuid4())

        # 创建工作目录
        work_dir = os.path.join('static', 'highlights', job_id)
        os.makedirs(work_dir, exist_ok=True)

        video_path = os.path.join(work_dir, filename)
        print(f"[API] 保存视频文件: {video_path}")
        video_file.save(video_path)

        # 检查文件大小
        file_size = os.path.getsize(video_path)
        print(f"[API] 文件大小: {file_size / 1024 / 1024:.2f} MB")

        # 初始化任务状态
        highlight_jobs[job_id] = {
            'status': 'processing',
            'current_step': 1,
            'progress': 0,
            'theme': theme,
            'video_path': video_path,
            'work_dir': work_dir,
            'step_messages': {
                1: '正在生成高光判定标准...',
                2: '等待中...',
                3: '等待中...',
                4: '等待中...',
                5: '等待中...',
                6: '等待中...'
            }
        }

        # 启动后台处理线程
        def process_highlight():
            try:
                job_status = highlight_jobs[job_id]
                print(f"\n{'='*80}")
                print(f"[高光提取] 开始处理任务: {job_id}")
                print(f"[高光提取] 主题: {theme}")
                print(f"[高光提取] 视频文件: {video_path}")
                print(f"{'='*80}\n")

                # 步骤1: 生成高光判定标准
                print(f"[步骤1] 开始生成高光判定标准...")
                job_status['current_step'] = 1
                job_status['progress'] = 5
                job_status['step_messages'][1] = '正在调用Claude Opus生成标准...'

                criteria = highlight_extractor.generate_criteria(theme)
                print(f"[步骤1] 标准生成完成，长度: {len(criteria)} 字符")
                print(f"[步骤1] 生成的标准:\n{criteria}\n")
                job_status['criteria'] = criteria
                job_status['step_messages'][1] = '✅ 标准生成完成'
                job_status['progress'] = 15

                # 步骤2: 压缩视频
                print(f"[步骤2] 开始压缩视频...")
                job_status['current_step'] = 2
                job_status['step_messages'][2] = '正在压缩视频...'

                compressed_path = os.path.join(work_dir, 'compressed.mp4')
                print(f"[步骤2] 输入视频: {video_path}")
                print(f"[步骤2] 输出路径: {compressed_path}")
                compressed_path = highlight_extractor.compress_video(video_path, compressed_path)
                print(f"[步骤2] 视频压缩完成: {compressed_path}")
                job_status['compressed_path'] = compressed_path
                job_status['step_messages'][2] = '✅ 视频压缩完成'
                job_status['progress'] = 25

                # 步骤3: AI分析视频
                print(f"[步骤3] 开始使用Nova Pro分析视频...")
                job_status['current_step'] = 3
                job_status['step_messages'][3] = '正在使用Nova Pro分析视频...'

                analysis = highlight_extractor.analyze_video(compressed_path, criteria)
                print(f"[步骤3] 视频分析完成，分析结果长度: {len(analysis)} 字符")
                print(f"[步骤3] 分析结果:\n{analysis}\n")
                job_status['analysis'] = analysis
                job_status['step_messages'][3] = '✅ 视频分析完成'
                job_status['progress'] = 45

                # 步骤4: 切片并生成向量（合并操作）
                print(f"[步骤4] 开始切片视频并生成向量嵌入...")
                job_status['current_step'] = 4
                job_status['step_messages'][4] = '正在切片视频并生成向量嵌入...'

                clips = highlight_extractor.extract_clips_with_embeddings(compressed_path, segment_duration=3)
                successful_clips = [c for c in clips if c.get('embedding') is not None]
                print(f"[步骤4] 完成！切片: {len(clips)}个, 向量成功: {len(successful_clips)}个")
                job_status['clips'] = clips
                job_status['step_messages'][4] = f'✅ 已切片 {len(clips)} 个片段，向量生成成功 {len(successful_clips)} 个'
                job_status['progress'] = 65

                # 步骤5: 匹配高光片段
                print(f"[步骤5] 开始匹配高光片段...")
                job_status['current_step'] = 5
                job_status['step_messages'][5] = '正在匹配高光片段...'

                selected_clips = highlight_extractor.match_clips(analysis, clips)
                print(f"[步骤5] 匹配完成，选中 {len(selected_clips)} 个高光片段")

                # 准备片段信息供前端展示
                clips_info = []
                for clip in selected_clips:
                    clips_info.append({
                        'url': '/' + clip['path'].replace('\\', '/'),
                        'timestamp': clip['timestamp'],
                        'similarity': clip['similarity'],
                        'description': clip.get('point', '')[:100]
                    })

                job_status['clips'] = clips_info
                job_status['clips_count'] = len(selected_clips)
                job_status['step_messages'][5] = f'✅ 匹配到 {len(selected_clips)} 个高光片段'
                job_status['progress'] = 85

                # 步骤6: 拼接高光视频
                print(f"[步骤6] 开始拼接高光视频...")
                job_status['current_step'] = 6
                job_status['step_messages'][6] = '正在拼接高光视频...'

                highlight_video_path = os.path.join(work_dir, 'highlight.mp4')
                print(f"[步骤6] 输出路径: {highlight_video_path}")
                highlight_extractor.create_highlight_video(selected_clips, highlight_video_path)
                print(f"[步骤6] 高光视频拼接完成")

                job_status['highlight_video_path'] = highlight_video_path
                job_status['highlight_video_url'] = '/' + highlight_video_path.replace('\\', '/')
                job_status['step_messages'][6] = '✅ 高光视频生成完成'
                job_status['progress'] = 100

                # 获取视频时长信息
                job_status['original_duration'] = highlight_extractor.get_video_duration(video_path)
                job_status['highlight_duration'] = highlight_extractor.get_video_duration(highlight_video_path)

                # 完成
                job_status['status'] = 'completed'
                job_status['current_step'] = 6

                print(f"\n{'='*80}")
                print(f"[高光提取] 任务完成: {job_id}")
                print(f"[高光提取] 原视频时长: {job_status.get('original_duration', 0):.2f}秒")
                print(f"[高光提取] 高光片段数: {job_status.get('clips_count', 0)}")
                print(f"[高光提取] 高光视频时长: {job_status.get('highlight_duration', 0):.2f}秒")
                print(f"[高光提取] 输出文件: {highlight_video_path}")
                print(f"{'='*80}\n")

            except Exception as e:
                print(f"\n{'='*80}")
                print(f"[错误] 处理失败: {job_id}")
                print(f"[错误] 错误信息: {str(e)}")
                print(f"[错误] 详细堆栈:")
                import traceback
                traceback.print_exc()
                print(f"{'='*80}\n")

                highlight_jobs[job_id]['status'] = 'failed'
                highlight_jobs[job_id]['error'] = str(e)

        # 启动后台线程
        thread = threading.Thread(target=process_highlight)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': '开始处理高光视频...'
        })

    except Exception as e:
        print(f"Error starting highlight extraction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/job-status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """获取高光提取任务状态"""
    try:
        if job_id not in highlight_jobs:
            return jsonify({'error': '任务不存在'}), 404

        job_status = highlight_jobs[job_id]

        return jsonify({
            'success': True,
            'status': job_status['status'],
            'current_step': job_status.get('current_step', 1),
            'progress': job_status.get('progress', 0),
            'step_messages': job_status.get('step_messages', {}),
            'criteria': job_status.get('criteria'),
            'analysis': job_status.get('analysis'),
            'clips': job_status.get('clips', []),
            'clips_count': job_status.get('clips_count', 0),
            'highlight_video_url': job_status.get('highlight_video_url'),
            'original_duration': job_status.get('original_duration', 0),
            'highlight_duration': job_status.get('highlight_duration', 0),
            'error': job_status.get('error')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-highlight/<job_id>', methods=['GET'])
def download_highlight(job_id):
    """下载生成的高光视频"""
    try:
        if job_id not in highlight_jobs:
            return jsonify({'error': '任务不存在'}), 404

        job_status = highlight_jobs[job_id]

        if job_status['status'] != 'completed':
            return jsonify({'error': '视频还未生成完成'}), 400

        video_path = job_status.get('highlight_video_path')
        if not video_path or not os.path.exists(video_path):
            return jsonify({'error': '视频文件不存在'}), 404

        return send_file(video_path, as_attachment=True, download_name='highlight_video.mp4', mimetype='video/mp4')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
