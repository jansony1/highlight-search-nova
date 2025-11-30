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
        this.waitingForConfirmation = false;
        this.confirmedCriteria = null;
        this.confirmedAnalysis = null;
        this.extractionMode = 'embedding';  // 'embedding' or 'direct'

        this.init();
    }

    init() {
        this.setupEventListeners();
    }

    setupEventListeners() {
        // 方法选择
        document.querySelectorAll('input[name="extraction-method"]').forEach(radio => {
            radio.addEventListener('change', (e) => this.handleMethodChange(e.target.value));
        });

        // 主题输入
        this.themeInput.addEventListener('input', () => this.updateStartButton());

        // 视频上传
        this.uploadArea.addEventListener('click', () => this.videoInput.click());
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

        // 确认按钮 - 语义匹配模式
        document.getElementById('confirm-criteria-btn')?.addEventListener('click', () => this.confirmCriteria());
        document.getElementById('confirm-analysis-btn')?.addEventListener('click', () => this.confirmAnalysis());

        // 确认按钮 - 直接定位模式
        document.getElementById('direct-confirm-summary-btn')?.addEventListener('click', () => this.directConfirmSummary());
        document.getElementById('direct-confirm-highlights-btn')?.addEventListener('click', () => this.directConfirmHighlights());
    }

    handleMethodChange(method) {
        this.extractionMode = method;

        // 切换UI显示
        const themeArea = document.getElementById('theme-input-area');
        const directHint = document.getElementById('direct-mode-hint');

        if (method === 'embedding') {
            themeArea.style.display = 'block';
            directHint.style.display = 'none';
        } else {
            themeArea.style.display = 'none';
            directHint.style.display = 'block';
        }

        this.updateStartButton();
    }

    handleFileSelect(file) {
        if (!file.type.startsWith('video/')) {
            alert('请选择视频文件');
            return;
        }

        const maxSize = 500 * 1024 * 1024;
        if (file.size > maxSize) {
            alert('视频文件过大，请选择小于500MB的文件');
            return;
        }

        this.selectedFile = file;
        this.videoName.textContent = file.name;

        const url = URL.createObjectURL(file);
        this.previewVideo.src = url;
        this.uploadArea.style.display = 'none';
        this.videoPreview.style.display = 'block';

        this.updateStartButton();
        this.updateSteps(2);
    }

    updateStartButton() {
        const hasVideo = this.selectedFile !== null;

        if (this.extractionMode === 'embedding') {
            const theme = this.themeInput.value.trim();
            this.startBtn.disabled = !(theme && hasVideo);
        } else {
            // 直接定位模式只需要视频
            this.startBtn.disabled = !hasVideo;
        }
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

        if (this.extractionMode === 'embedding') {
            await this.startEmbeddingMode();
        } else {
            await this.startDirectMode();
        }
    }

    async startEmbeddingMode() {
        // 显示进度区域
        document.getElementById('progress-section').style.display = 'block';
        document.getElementById('direct-progress-section').style.display = 'none';
        this.updateSteps(3);

        const formData = new FormData();
        formData.append('theme', this.themeInput.value.trim());
        formData.append('video', this.selectedFile);

        try {
            const response = await fetch('/api/extract-highlight', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('处理请求失败');
            }

            const result = await response.json();
            this.jobId = result.job_id;

            this.startPolling();

        } catch (error) {
            console.error('Error:', error);
            alert('处理失败：' + error.message);
            this.startBtn.disabled = false;
            this.startBtn.textContent = '🚀 开始处理并生成高光视频';
        }
    }

    async startDirectMode() {
        // 显示直接定位进度区域
        document.getElementById('direct-progress-section').style.display = 'block';
        document.getElementById('progress-section').style.display = 'none';
        this.updateSteps(3);

        const formData = new FormData();
        formData.append('video', this.selectedFile);

        try {
            const response = await fetch('/api/extract-direct', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('处理请求失败');
            }

            const result = await response.json();
            this.jobId = result.job_id;

            this.startDirectPolling();

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
        }, 2000);
    }

    startDirectPolling() {
        this.pollingInterval = setInterval(() => {
            this.checkDirectJobStatus();
        }, 2000);
    }

    async checkJobStatus() {
        try {
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

    async checkDirectJobStatus() {
        try {
            const response = await fetch(`/api/job-status/${this.jobId}`);
            if (!response.ok) {
                throw new Error('获取状态失败');
            }

            const status = await response.json();
            this.updateDirectProgress(status);

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
        this.confirmedCriteria = document.getElementById('criteria-inline-content').value;
        document.getElementById('criteria-inline-content').disabled = true;
        document.getElementById('confirm-criteria-btn').disabled = true;
        document.getElementById('confirm-criteria-btn').textContent = '✓ 已确认';
        this.waitingForConfirmation = false;

        fetch(`/api/confirm-criteria/${this.jobId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({criteria: this.confirmedCriteria})
        }).catch(err => console.error('Failed to save criteria:', err));
    }

    confirmAnalysis() {
        this.confirmedAnalysis = document.getElementById('analysis-inline-content').value;
        document.getElementById('analysis-inline-content').disabled = true;
        document.getElementById('confirm-analysis-btn').disabled = true;
        document.getElementById('confirm-analysis-btn').textContent = '✓ 已确认';
        this.waitingForConfirmation = false;

        fetch(`/api/confirm-analysis/${this.jobId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({analysis: this.confirmedAnalysis})
        }).catch(err => console.error('Failed to save analysis:', err));
    }

    async directConfirmSummary() {
        console.log('[DirectMode] Confirming summary, jobId:', this.jobId);
        const criteria = document.getElementById('direct-criteria-content').value;
        console.log('[DirectMode] Criteria length:', criteria.length);

        document.getElementById('direct-criteria-content').disabled = true;
        document.getElementById('direct-confirm-summary-btn').disabled = true;
        document.getElementById('direct-confirm-summary-btn').textContent = '✓ 已确认';

        try {
            const response = await fetch(`/api/direct-confirm-summary/${this.jobId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({criteria: criteria})
            });
            console.log('[DirectMode] Confirmation response status:', response.status);
            if (!response.ok) {
                const error = await response.json();
                console.error('[DirectMode] Confirmation failed:', error);
            }
        } catch (error) {
            console.error('[DirectMode] Failed to confirm summary:', error);
        }
    }

    async directConfirmHighlights() {
        const highlightsJson = document.getElementById('direct-highlights-content').value;

        try {
            const highlights = JSON.parse(highlightsJson);

            document.getElementById('direct-highlights-content').disabled = true;
            document.getElementById('direct-confirm-highlights-btn').disabled = true;
            document.getElementById('direct-confirm-highlights-btn').textContent = '✓ 已确认';

            await fetch(`/api/direct-confirm-highlights/${this.jobId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({highlights: highlights})
            });
        } catch (error) {
            alert('JSON格式错误，请检查！');
            console.error('JSON parse error:', error);
        }
    }

    updateProgress(status) {
        const step = status.current_step || 1;
        const progress = status.progress || 0;

        document.getElementById('progress-bar-fill').style.width = progress + '%';
        document.getElementById('progress-text').textContent = Math.round(progress) + '%';

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

            const statusEl = stepEl.querySelector('.progress-step-status');
            if (status.step_messages && status.step_messages[i]) {
                statusEl.textContent = status.step_messages[i];
            }
        }

        // 显示生成的标准
        if (status.criteria && !this.confirmedCriteria) {
            const criteriaInline = document.getElementById('criteria-inline');
            if (criteriaInline && (criteriaInline.style.display === 'none' || !criteriaInline.style.display)) {
                document.getElementById('criteria-inline-content').value = status.criteria;
                criteriaInline.style.display = 'block';
                this.waitingForConfirmation = true;
            }
        }

        // 显示分析结果
        if (status.analysis && !this.confirmedAnalysis) {
            const analysisInline = document.getElementById('analysis-inline');
            if (analysisInline && (analysisInline.style.display === 'none' || !analysisInline.style.display)) {
                document.getElementById('analysis-inline-content').value = status.analysis;
                analysisInline.style.display = 'block';
                this.waitingForConfirmation = true;
            }
        }

        // 显示匹配的片段
        if (status.clips && status.clips.length > 0) {
            this.showClips(status.clips);
        }
    }

    updateDirectProgress(status) {
        const step = status.current_step || 1;
        const progress = status.progress || 0;

        document.getElementById('direct-progress-bar-fill').style.width = progress + '%';
        document.getElementById('direct-progress-text').textContent = Math.round(progress) + '%';

        for (let i = 1; i <= 3; i++) {
            const stepEl = document.getElementById(`direct-step-${i}`);
            if (i < step) {
                stepEl.classList.remove('active');
                stepEl.classList.add('completed');
            } else if (i === step) {
                stepEl.classList.add('active');
                stepEl.classList.remove('completed');
            } else {
                stepEl.classList.remove('active', 'completed');
            }

            const statusEl = stepEl.querySelector('.progress-step-status');
            if (status.step_messages && status.step_messages[i]) {
                statusEl.textContent = status.step_messages[i];
            }
        }

        // 显示总结和标准
        if (status.summary && status.criteria && status.waiting_for === 'summary_confirmation') {
            const summaryInline = document.getElementById('direct-summary-inline');
            if (summaryInline && (summaryInline.style.display === 'none' || !summaryInline.style.display)) {
                document.getElementById('direct-summary-content').textContent = status.summary;
                document.getElementById('direct-criteria-content').value = status.criteria;
                summaryInline.style.display = 'block';
            }
        }

        // 显示高光片段
        if (status.highlights_data && status.waiting_for === 'highlights_confirmation') {
            const highlightsInline = document.getElementById('direct-highlights-inline');
            if (highlightsInline && (highlightsInline.style.display === 'none' || !highlightsInline.style.display)) {
                document.getElementById('direct-highlights-content').value = JSON.stringify(status.highlights_data, null, 2);
                highlightsInline.style.display = 'block';
            }
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

        const resultSection = document.getElementById('result-section');
        const resultVideo = document.getElementById('result-video');

        resultVideo.src = status.highlight_video_url;
        resultSection.style.display = 'block';

        // 显示使用的标准和分析
        if (this.extractionMode === 'embedding') {
            if (this.confirmedCriteria || status.criteria) {
                document.getElementById('final-criteria').textContent = this.confirmedCriteria || status.criteria;
            }
            if (this.confirmedAnalysis || status.analysis) {
                document.getElementById('final-analysis').textContent = this.confirmedAnalysis || status.analysis;
            }
        } else {
            // 直接定位模式
            if (status.confirmed_criteria || status.criteria) {
                document.getElementById('final-criteria').textContent = status.confirmed_criteria || status.criteria;
            }
            if (status.final_highlights) {
                const highlightsList = status.final_highlights.map((h, i) =>
                    `${i+1}. [${h.start_time.toFixed(1)}s - ${h.end_time.toFixed(1)}s] ${h.description}`
                ).join('\n');
                document.getElementById('final-analysis').textContent = highlightsList;
            }
        }

        // 更新统计信息
        document.getElementById('original-duration').textContent = this.formatTime(status.original_duration || 0);
        document.getElementById('clips-count').textContent = status.clips_count || 0;
        document.getElementById('highlight-duration').textContent = this.formatTime(status.highlight_duration || 0);

        // 隐藏进度区域
        document.getElementById('progress-section').style.display = 'none';
        document.getElementById('direct-progress-section').style.display = 'none';

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
