class HighlightExtractor {
    constructor() {
        this.themeInput = document.getElementById('theme-input');
        this.videoInput = document.getElementById('video-input');
        this.uploadArea = document.getElementById('video-upload-area');
        this.videoPreview = document.getElementById('video-preview');
        this.previewVideo = document.getElementById('preview-video');
        this.videoName = document.getElementById('video-name');
        this.startBtn = document.getElementById('start-process-btn');
        this.changeVideoBtn = document.getElementById('change-video-btn');
        this.selectedFile = null;
        this.jobId = null;
        this.pollingInterval = null;
        this.waitingForConfirmation = false;  // 是否在等待用户确认
        this.confirmedCriteria = null;  // 用户确认的标准
        this.confirmedAnalysis = null;  // 用户确认的分析

        this.init();
    }

    init() {
        this.setupEventListeners();
    }

    setupEventListeners() {
        // 主题输入
        this.themeInput.addEventListener('input', () => this.updateStartButton());

        // 视频上传区域点击
        this.uploadArea.addEventListener('click', () => this.videoInput.click());

        // 文件选择
        this.videoInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });

        // 拖拽上传
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('dragover');
        });

        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('dragover');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        // 更换视频按钮
        this.changeVideoBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.videoInput.click();
        });

        // 开始处理按钮
        this.startBtn.addEventListener('click', () => this.startProcessing());

        // 下载和重新开始按钮
        document.getElementById('download-btn')?.addEventListener('click', () => this.downloadVideo());
        document.getElementById('restart-btn')?.addEventListener('click', () => this.restart());

        // 确认按钮
        document.getElementById('confirm-criteria-btn')?.addEventListener('click', () => this.confirmCriteria());
        document.getElementById('confirm-analysis-btn')?.addEventListener('click', () => this.confirmAnalysis());
    }

    handleFileSelect(file) {
        if (!file.type.startsWith('video/')) {
            alert('请选择视频文件');
            return;
        }

        const maxSize = 500 * 1024 * 1024; // 500MB
        if (file.size > maxSize) {
            alert('视频文件过大，请选择小于500MB的文件');
            return;
        }

        this.selectedFile = file;
        this.videoName.textContent = file.name;

        // 显示视频预览
        const url = URL.createObjectURL(file);
        this.previewVideo.src = url;
        this.uploadArea.style.display = 'none';
        this.videoPreview.style.display = 'block';

        this.updateStartButton();
        this.updateSteps(2);
    }

    updateStartButton() {
        const theme = this.themeInput.value.trim();
        const hasVideo = this.selectedFile !== null;
        this.startBtn.disabled = !(theme && hasVideo);
    }

    updateSteps(step) {
        const steps = document.querySelectorAll('.step');
        steps.forEach((s, index) => {
            if (index < step) {
                s.classList.add('completed');
                s.classList.remove('active');
            } else if (index === step - 1) {
                s.classList.add('active');
                s.classList.remove('completed');
            } else {
                s.classList.remove('active', 'completed');
            }
        });
    }

    async startProcessing() {
        this.startBtn.disabled = true;
        this.startBtn.textContent = '处理中...';

        // 显示进度区域
        document.getElementById('progress-section').style.display = 'block';
        this.updateSteps(3);

        // 准备表单数据
        const formData = new FormData();
        formData.append('theme', this.themeInput.value.trim());
        formData.append('video', this.selectedFile);

        try {
            // 发送请求
            const response = await fetch('/api/extract-highlight', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('处理请求失败');
            }

            const result = await response.json();
            this.jobId = result.job_id;

            // 开始轮询状态
            this.startPolling();

        } catch (error) {
            console.error('Error:', error);
            alert('处理失败：' + error.message);
            this.startBtn.disabled = false;
            this.startBtn.textContent = '🚀 开始处理并生成高光视频';
        }
    }

    startPolling() {
        this.pollingInterval = setInterval(() => {
            this.checkJobStatus();
        }, 2000); // 每2秒检查一次
    }

    async checkJobStatus() {
        try {
            // 如果正在等待用户确认，暂停轮询
            if (this.waitingForConfirmation) {
                return;
            }

            const response = await fetch(`/api/job-status/${this.jobId}`);
            if (!response.ok) {
                throw new Error('获取状态失败');
            }

            const status = await response.json();
            this.updateProgress(status);

            if (status.status === 'completed') {
                clearInterval(this.pollingInterval);
                this.showResults(status);
            } else if (status.status === 'failed') {
                clearInterval(this.pollingInterval);
                alert('处理失败：' + status.error);
                this.restart();
            }

        } catch (error) {
            console.error('Error checking status:', error);
        }
    }

    confirmCriteria() {
        // 获取用户编辑后的标准
        this.confirmedCriteria = document.getElementById('criteria-inline-content').value;

        // 禁用编辑和按钮
        document.getElementById('criteria-inline-content').disabled = true;
        document.getElementById('confirm-criteria-btn').disabled = true;
        document.getElementById('confirm-criteria-btn').textContent = '✓ 已确认';

        // 恢复轮询
        this.waitingForConfirmation = false;

        console.log('Criteria confirmed:', this.confirmedCriteria);

        // 发送确认的标准到后端（可选，用于更新任务状态）
        fetch(`/api/confirm-criteria/${this.jobId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({criteria: this.confirmedCriteria})
        }).catch(err => console.error('Failed to save criteria:', err));
    }

    confirmAnalysis() {
        // 获取用户编辑后的分析
        this.confirmedAnalysis = document.getElementById('analysis-inline-content').value;

        // 禁用编辑和按钮
        document.getElementById('analysis-inline-content').disabled = true;
        document.getElementById('confirm-analysis-btn').disabled = true;
        document.getElementById('confirm-analysis-btn').textContent = '✓ 已确认';

        // 恢复轮询
        this.waitingForConfirmation = false;

        console.log('Analysis confirmed:', this.confirmedAnalysis);

        // 发送确认的分析到后端（可选）
        fetch(`/api/confirm-analysis/${this.jobId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({analysis: this.confirmedAnalysis})
        }).catch(err => console.error('Failed to save analysis:', err));
    }

    updateProgress(status) {
        const step = status.current_step || 1;
        const progress = status.progress || 0;

        // 更新进度条
        document.getElementById('progress-bar-fill').style.width = progress + '%';
        document.getElementById('progress-text').textContent = Math.round(progress) + '%';

        // 更新步骤状态
        for (let i = 1; i <= 6; i++) {
            const stepEl = document.getElementById(`progress-step-${i}`);
            if (i < step) {
                stepEl.classList.remove('active');
                stepEl.classList.add('completed');
            } else if (i === step) {
                stepEl.classList.add('active');
                stepEl.classList.remove('completed');
            } else {
                stepEl.classList.remove('active', 'completed');
            }

            // 更新状态文本
            const statusEl = stepEl.querySelector('.progress-step-status');
            if (status.step_messages && status.step_messages[i]) {
                statusEl.textContent = status.step_messages[i];
            }
        }

        // 显示生成的标准（在步骤1下方）并暂停轮询等待确认
        if (status.criteria && !this.confirmedCriteria) {
            const criteriaInline = document.getElementById('criteria-inline');
            if (criteriaInline && (criteriaInline.style.display === 'none' || !criteriaInline.style.display)) {
                document.getElementById('criteria-inline-content').value = status.criteria;
                criteriaInline.style.display = 'block';

                // 暂停轮询，等待用户确认
                this.waitingForConfirmation = true;
            }
        }

        // 显示分析结果（在步骤3下方）并暂停轮询等待确认
        if (status.analysis && !this.confirmedAnalysis) {
            const analysisInline = document.getElementById('analysis-inline');
            if (analysisInline && (analysisInline.style.display === 'none' || !analysisInline.style.display)) {
                document.getElementById('analysis-inline-content').value = status.analysis;
                analysisInline.style.display = 'block';

                // 暂停轮询，等待用户确认
                this.waitingForConfirmation = true;
            }
        }

        // 显示匹配的片段
        if (status.clips && status.clips.length > 0) {
            this.showClips(status.clips);
        }
    }

    showClips(clips) {
        const container = document.getElementById('clips-container');
        container.innerHTML = '';

        clips.forEach((clip, index) => {
            const clipCard = document.createElement('div');
            clipCard.className = 'clip-card';
            clipCard.innerHTML = `
                <video class="clip-video" src="${clip.url}" controls></video>
                <div class="clip-info">
                    <div class="clip-title">片段 ${index + 1}</div>
                    <div>${clip.description || ''}</div>
                    <div class="clip-meta">
                        <span class="clip-timestamp">⏱️ ${this.formatTime(clip.timestamp)}</span>
                        <span class="clip-similarity">🎯 相似度: ${(clip.similarity * 100).toFixed(1)}%</span>
                    </div>
                </div>
            `;
            container.appendChild(clipCard);
        });

        document.getElementById('clips-section').style.display = 'block';
    }

    showResults(status) {
        this.updateSteps(4);

        // 显示最终结果
        const resultSection = document.getElementById('result-section');
        const resultVideo = document.getElementById('result-video');

        resultVideo.src = status.highlight_video_url;
        resultSection.style.display = 'block';

        // 显示使用的标准和分析结果
        if (this.confirmedCriteria || status.criteria) {
            document.getElementById('final-criteria').textContent = this.confirmedCriteria || status.criteria;
        }
        if (this.confirmedAnalysis || status.analysis) {
            document.getElementById('final-analysis').textContent = this.confirmedAnalysis || status.analysis;
        }

        // 更新统计信息
        document.getElementById('original-duration').textContent = this.formatTime(status.original_duration || 0);
        document.getElementById('clips-count').textContent = status.clips_count || 0;
        document.getElementById('highlight-duration').textContent = this.formatTime(status.highlight_duration || 0);

        // 隐藏进度区域
        document.getElementById('progress-section').style.display = 'none';

        // 滚动到结果
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    async downloadVideo() {
        if (!this.jobId) return;

        try {
            const response = await fetch(`/api/download-highlight/${this.jobId}`);
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'highlight_video.mp4';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Download error:', error);
            alert('下载失败');
        }
    }

    restart() {
        location.reload();
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new HighlightExtractor();
});
