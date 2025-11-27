class NovaEmbeddingApp {
    constructor() {
        this.currentTab = 'image';
        this.selectedFile = null;
        this.init();
    }

    init() {
        this.setupTabs();
        this.setupFileUpload();
        this.setupSearch();
    }

    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabContents = document.querySelectorAll('.tab-content');

        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabName = button.dataset.tab;
                
                // 更新按钮状态
                tabButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
                
                // 更新内容显示
                tabContents.forEach(content => content.classList.remove('active'));
                document.getElementById(`${tabName}-tab`).classList.add('active');
                
                this.currentTab = tabName;
                this.selectedFile = null;
                this.updateUploadButton();
            });
        });
    }

    setupFileUpload() {
        const uploadAreas = document.querySelectorAll('.upload-area');
        const uploadBtn = document.getElementById('upload-btn');

        uploadAreas.forEach(area => {
            const fileInput = area.querySelector('.file-input');
            
            // 点击上传区域
            area.addEventListener('click', () => {
                if (fileInput) fileInput.click();
            });

            // 文件选择
            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    this.handleFileSelect(e.target.files[0]);
                });
            }

            // 拖拽功能
            area.addEventListener('dragover', (e) => {
                e.preventDefault();
                area.classList.add('dragover');
            });

            area.addEventListener('dragleave', () => {
                area.classList.remove('dragover');
            });

            area.addEventListener('drop', (e) => {
                e.preventDefault();
                area.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    this.handleFileSelect(files[0]);
                }
            });
        });

        // 文本输入框实时验证
        const textInputs = document.querySelectorAll('.text-input');
        textInputs.forEach(input => {
            input.addEventListener('input', () => {
                this.updateUploadButton();
            });
        });

        // 上传按钮
        uploadBtn.addEventListener('click', () => {
            this.uploadFile();
        });
    }

    setupSearch() {
        const searchBtn = document.getElementById('search-btn');
        const searchInput = document.querySelector('.search-input');

        searchBtn.addEventListener('click', () => {
            const query = searchInput.value.trim();
            if (query) {
                this.performSearch(query);
            }
        });

        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const query = e.target.value.trim();
                if (query) {
                    this.performSearch(query);
                }
            }
        });
    }

    handleFileSelect(file) {
        this.selectedFile = file;
        this.updateUploadButton();
        
        // 更新显示
        const activeTab = document.querySelector('.tab-content.active');
        const uploadArea = activeTab.querySelector('.upload-area');
        const uploadText = uploadArea.querySelector('.upload-text');
        
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        uploadText.textContent = `已选择: ${file.name} (${sizeMB}MB)`;
    }

    updateUploadButton() {
        const uploadBtn = document.getElementById('upload-btn');
        const activeTab = document.querySelector('.tab-content.active');
        
        if (this.currentTab === 'text') {
            const textInput = activeTab.querySelector('.text-input');
            uploadBtn.disabled = !textInput.value.trim();
        } else {
            uploadBtn.disabled = !this.selectedFile;
        }
    }

    async uploadFile() {
        const uploadBtn = document.getElementById('upload-btn');
        const activeTab = document.querySelector('.tab-content.active');
        const dimensionSelect = document.getElementById('embedding-dimension');
        
        uploadBtn.disabled = true;
        uploadBtn.textContent = '上传中...';

        try {
            const formData = new FormData();
            
            // 添加embedding维度参数
            const embeddingDimension = dimensionSelect.value;
            formData.append('embedding_dimension', embeddingDimension);
            
            if (this.currentTab === 'text') {
                const textInput = activeTab.querySelector('.text-input');
                const textBlob = new Blob([textInput.value], { type: 'text/plain' });
                formData.append('file', textBlob, 'text_input.txt');
                formData.append('type', 'text');
            } else {
                formData.append('file', this.selectedFile);
                formData.append('type', this.currentTab);
                
                const textInput = activeTab.querySelector('.text-input');
                if (textInput && textInput.value.trim()) {
                    formData.append('text', textInput.value.trim());
                }
            }

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                if (result.async_processing) {
                    this.showMessage(`${result.message}`, 'success');
                    this.showAsyncProcessingStatus(result.file_id, result.filename || this.selectedFile?.name);
                    this.startAsyncStatusCheck(result.file_id);
                } else {
                    this.showMessage('文件上传成功！Embedding已生成。', 'success');
                }
                this.resetForm();
            } else {
                this.showMessage(`上传失败: ${result.error}`, 'error');
            }

        } catch (error) {
            this.showMessage(`上传失败: ${error.message}`, 'error');
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = '上传并生成Embedding';
        }
    }

    showAsyncProcessingStatus(fileId, filename) {
        // 创建处理状态显示区域
        const statusDiv = document.createElement('div');
        statusDiv.id = `async-status-${fileId}`;
        statusDiv.className = 'async-status';
        statusDiv.innerHTML = `
            <div style="background: #e8f4fd; border: 1px solid #0066c0; border-radius: 4px; padding: 1rem; margin: 1rem 0;">
                <div style="display: flex; align-items: center; margin-bottom: 0.5rem;">
                    <div class="spinner" style="width: 16px; height: 16px; border: 2px solid #f3f3f3; border-top: 2px solid #0066c0; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 0.5rem;"></div>
                    <strong>正在处理: ${filename}</strong>
                </div>
                <div style="font-size: 0.9rem; color: #666;">
                    文件已上传到S3，正在生成embedding向量...
                </div>
                <div style="font-size: 0.8rem; color: #888; margin-top: 0.5rem;">
                    文件ID: ${fileId}
                </div>
            </div>
        `;

        // 添加CSS动画
        if (!document.querySelector('#spinner-style')) {
            const style = document.createElement('style');
            style.id = 'spinner-style';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }

        // 插入到结果区域
        const resultsSection = document.querySelector('.results-section');
        resultsSection.insertBefore(statusDiv, resultsSection.firstChild.nextSibling);
    }

    startAsyncStatusCheck(fileId) {
        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/async-status/${fileId}`);
                const result = await response.json();
                
                if (result.success) {
                    const statusDiv = document.getElementById(`async-status-${fileId}`);
                    
                    if (result.status === 'completed') {
                        if (statusDiv) {
                            statusDiv.innerHTML = `
                                <div style="background: #eafaf1; border: 1px solid #067d62; border-radius: 4px; padding: 1rem; margin: 1rem 0;">
                                    <div style="display: flex; align-items: center; margin-bottom: 0.5rem;">
                                        <span style="color: #067d62; margin-right: 0.5rem;">✓</span>
                                        <strong>处理完成: ${result.filename}</strong>
                                    </div>
                                    <div style="font-size: 0.9rem; color: #067d62;">
                                        Embedding已生成完成！${result.segments ? `(${result.segments} 个分段)` : ''} 现在可以进行搜索。
                                    </div>
                                </div>
                            `;
                            // 5秒后自动移除
                            setTimeout(() => statusDiv.remove(), 5000);
                        }
                        this.showMessage(`异步处理完成！文件 ${result.filename} 的embedding已生成。`, 'success');
                        return; // 停止检查
                    } else if (result.status === 'failed') {
                        if (statusDiv) {
                            statusDiv.innerHTML = `
                                <div style="background: #ffeaea; border: 1px solid #c40000; border-radius: 4px; padding: 1rem; margin: 1rem 0;">
                                    <div style="display: flex; align-items: center; margin-bottom: 0.5rem;">
                                        <span style="color: #c40000; margin-right: 0.5rem;">✗</span>
                                        <strong>处理失败: ${result.filename}</strong>
                                    </div>
                                    <div style="font-size: 0.9rem; color: #c40000;">
                                        错误: ${result.error}
                                    </div>
                                </div>
                            `;
                        }
                        this.showMessage(`异步处理失败: ${result.error}`, 'error');
                        return; // 停止检查
                    } else if (result.status === 'processing') {
                        // 更新处理状态
                        if (statusDiv) {
                            const timeElapsed = Math.floor((Date.now() - (statusDiv.dataset.startTime || Date.now())) / 1000);
                            statusDiv.dataset.startTime = statusDiv.dataset.startTime || Date.now();
                            
                            const statusText = statusDiv.querySelector('div:nth-child(2)');
                            if (statusText) {
                                statusText.textContent = `文件已上传到S3，正在生成embedding向量... (${timeElapsed}秒)`;
                            }
                        }
                        // 继续检查
                        setTimeout(checkStatus, 10000); // 10秒后再次检查
                    }
                }
            } catch (error) {
                console.error('检查异步状态失败:', error);
                setTimeout(checkStatus, 15000); // 出错后15秒重试
            }
        };
        
        // 开始状态检查
        setTimeout(checkStatus, 5000); // 5秒后开始第一次检查
    }

    async performSearch(query) {
        console.log('开始搜索:', query);
        
        const searchBtn = document.getElementById('search-btn');
        const resultsContainer = document.getElementById('results-container');
        const searchDimensionSelect = document.getElementById('search-dimension');

        // 检查按钮状态
        if (searchBtn.disabled) {
            console.log('按钮已禁用，跳过搜索');
            return;
        }

        // 获取选择的搜索维度
        const selectedDimension = searchDimensionSelect.value;
        console.log('选择的搜索维度:', selectedDimension);

        // 重置按钮状态
        searchBtn.disabled = true;
        searchBtn.textContent = '搜索中...';
        resultsContainer.innerHTML = '<div class="loading">正在搜索...</div>';
        
        console.log('按钮状态已设置为禁用');

        try {
            // 添加30秒超时
            const controller = new AbortController();
            const timeoutId = setTimeout(() => {
                console.log('搜索超时，中止请求');
                controller.abort();
            }, 30000);

            console.log('发送搜索请求...');
            
            // 构建请求体，包含维度信息
            const requestBody = { 
                query, 
                top_k: 5
            };
            
            // 如果不是自动检测，添加维度参数
            if (selectedDimension !== 'auto') {
                requestBody.search_dimension = parseInt(selectedDimension);
            }
            
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            console.log('收到响应:', response.status);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('解析结果:', result);

            if (result.success) {
                this.displayResults(result.results);
                console.log('结果显示完成');
            } else {
                this.showMessage(`搜索失败: ${result.error}`, 'error');
                resultsContainer.innerHTML = '<div class="no-results">搜索失败</div>';
            }

        } catch (error) {
            console.error('搜索错误:', error);
            if (error.name === 'AbortError') {
                this.showMessage('搜索超时，请重试', 'error');
            } else {
                this.showMessage(`搜索失败: ${error.message}`, 'error');
            }
            resultsContainer.innerHTML = '<div class="no-results">搜索失败</div>';
        } finally {
            // 确保按钮状态被重置
            console.log('重置按钮状态');
            searchBtn.disabled = false;
            searchBtn.textContent = '🔍 搜索相似内容';
        }
    }

    displayResults(results) {
        const resultsContainer = document.getElementById('results-container');
        
        if (results.length === 0) {
            resultsContainer.innerHTML = '<p>未找到相关结果</p>';
            return;
        }

        const resultsHtml = results.map((result, index) => {
            const meta = result.metadata;
            const isSegment = meta.segment_number !== undefined;
            
            let segmentInfo = '';
            if (isSegment) {
                segmentInfo = `
                    <p><strong>片段信息:</strong> 第${meta.segment_number}段 
                    ${meta.start_time !== undefined ? `(${meta.start_time.toFixed(2)}s - ${meta.end_time.toFixed(2)}s)` : ''}
                    </p>
                `;
            }
            
            let filePath = '';
            if (meta.s3_url) {
                filePath = `<p><strong>文件路径:</strong> ${meta.s3_url}</p>`;
            }
            
            let parentInfo = '';
            if (meta.parent_file_id) {
                parentInfo = `<p><strong>原文件ID:</strong> ${meta.parent_file_id}</p>`;
            }
            
            return `
                <div class="result-item">
                    <div class="result-header">
                        <span class="result-type">${meta.file_type}${isSegment ? ' 片段' : ''}</span>
                        <span class="similarity-score">相似度: ${(result.similarity * 100).toFixed(1)}%</span>
                    </div>
                    <h3>${meta.filename}</h3>
                    ${meta.text ? `<p><strong>描述:</strong> ${meta.text}</p>` : ''}
                    ${segmentInfo}
                    ${filePath}
                    ${parentInfo}
                    <p><strong>结果ID:</strong> ${result.id}</p>
                </div>
            `;
        }).join('');

        resultsContainer.innerHTML = resultsHtml;
    }

    showMessage(message, type) {
        // 移除现有的消息
        const existingMessages = document.querySelectorAll('.success, .error');
        existingMessages.forEach(msg => msg.remove());
        
        const container = document.querySelector('.main-content .container');
        const messageDiv = document.createElement('div');
        messageDiv.className = type;
        messageDiv.textContent = message;
        messageDiv.style.marginBottom = '1rem';
        
        // 插入到第一个section之前
        const firstSection = container.querySelector('section');
        container.insertBefore(messageDiv, firstSection);
        
        // 滚动到顶部显示消息
        window.scrollTo({ top: 0, behavior: 'smooth' });
        
        setTimeout(() => {
            messageDiv.remove();
        }, 5000);
    }

    resetForm() {
        this.selectedFile = null;
        const activeTab = document.querySelector('.tab-content.active');
        const uploadArea = activeTab.querySelector('.upload-area');
        const uploadText = uploadArea.querySelector('.upload-text');
        const textInputs = activeTab.querySelectorAll('.text-input');
        
        // 重置显示文本
        if (this.currentTab === 'image') {
            uploadText.textContent = '点击或拖拽图像文件到此处';
        } else if (this.currentTab === 'video') {
            uploadText.textContent = '点击或拖拽视频文件到此处';
        } else if (this.currentTab === 'audio') {
            uploadText.textContent = '点击或拖拽音频文件到此处';
        }
        
        // 清空输入框
        textInputs.forEach(input => input.value = '');
        
        this.updateUploadButton();
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new NovaEmbeddingApp();
});
