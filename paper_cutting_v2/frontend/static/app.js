// API 配置
const API_BASE = 'http://localhost:8000/api';

// 全局状态
let currentData = null;
let currentImagePath = null;
let currentStage = 'none'; // none, aliyun, glm
let currentViewMode = 'markdown'; // markdown, json

// DOM 元素
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const optimizeBtn = document.getElementById('optimizeBtn');
const gradeLevel = document.getElementById('gradeLevel');
const subject = document.getElementById('subject');
const imageContainer = document.getElementById('imageContainer');
const resultContainer = document.getElementById('resultContainer');
const imageStatus = document.getElementById('imageStatus');
const resultStatus = document.getElementById('resultStatus');
const loading = document.getElementById('loading');
const loadingText = document.getElementById('loadingText');
const loadingHint = document.getElementById('loadingHint');

// 事件监听
uploadBtn.addEventListener('click', handleUpload);
optimizeBtn.addEventListener('click', handleOptimize);

document.addEventListener('DOMContentLoaded', () => {
    console.log('📝 试卷识别 Demo 已加载');
    console.log('API 地址:', API_BASE);
});

// Tab 切换
function switchTab(mode) {
    currentViewMode = mode;

    // 更新按钮状态
    document.getElementById('tabMarkdown').classList.toggle('active', mode === 'markdown');
    document.getElementById('tabJSON').classList.toggle('active', mode === 'json');
    document.getElementById('tabRawJSON').classList.toggle('active', mode === 'raw_json');

    // 更新显示
    updateResultView();
}

// 上传并识别
async function handleUpload() {
    const file = fileInput.files[0];
    if (!file) {
        alert('请选择图片文件');
        return;
    }

    showLoading('阿里云识别中...', '预计 5-10 秒');
    updateStatus('imageStatus', 'processing', '上传中');
    updateStatus('resultStatus', 'processing', '识别中');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.status === 'success') {
            currentData = data;
            currentImagePath = data.image_path;
            currentStage = 'aliyun';

            // 调试日志
            console.log('✓ 阿里云识别成功');
            console.log('  - 题目数量:', data.aliyun_result?.parts?.[0]?.questions?.length || 0);
            console.log('  - Markdown 长度:', data.markdown?.length || 0);

            // 显示图片
            displayImage(file);
            updateStatus('imageStatus', 'success', '已加载');

            // 显示结果
            updateResultView();
            updateStatus('resultStatus', 'success', '阿里云识别完成');

            // 启用优化按钮
            optimizeBtn.disabled = false;
        } else {
            alert('识别失败：' + data.message);
            updateStatus('imageStatus', '', '识别失败');
            updateStatus('resultStatus', '', '识别失败');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('请求失败：' + error.message);
        updateStatus('imageStatus', '', '请求失败');
        updateStatus('resultStatus', '', '请求失败');
    } finally {
        hideLoading();
    }
}

// GLM 优化
async function handleOptimize() {
    if (!currentData) return;

    showLoading('GLM 优化中...', '预计 30-60 秒，请耐心等待');
    updateStatus('resultStatus', 'processing', 'GLM 优化中');

    try {
        const response = await fetch(`${API_BASE}/optimize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_path: currentImagePath,
                aliyun_result: currentData.aliyun_result,
                original_filename: currentData.original_filename,
                grade_level: gradeLevel.value,
                subject: subject.value
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            // 更新当前数据
            currentData = {
                ...currentData,
                glm_result: data.glm_result,
                glm_markdown: data.markdown,
                glm_json: data.json
            };

            currentStage = 'glm';

            // 更新显示
            updateResultView();
            updateStatus('resultStatus', 'success', 'GLM 优化完成');

            console.log('✓ GLM 优化成功', data);
        } else {
            alert('优化失败：' + data.message);
            updateStatus('resultStatus', '', '优化失败');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('请求失败：' + error.message);
        updateStatus('resultStatus', '', '请求失败');
    } finally {
        hideLoading();
    }
}

// 显示图片
function displayImage(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        // 构建相对定位容器，内含图片和 overlay 层
        imageContainer.innerHTML = `
            <div id="imageWrapper" style="position:relative;display:inline-block;width:100%;">
                <img id="paperImg" src="${e.target.result}" alt="试卷图片" style="width:100%;display:block;">
                <div id="overlayLayer" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;"></div>
            </div>`;
        // 图片加载完成后建立高亮框
        document.getElementById('paperImg').addEventListener('load', () => {
            if (currentData) buildImageOverlays();
        });
        // 如果图片已缓存直接建立
        const img = document.getElementById('paperImg');
        if (img.complete) {
            if (currentData) buildImageOverlays();
        }
    };
    reader.readAsDataURL(file);
}

// 根据题目坐标在图片上建立高亮 overlay
function buildImageOverlays() {
    const img = document.getElementById('paperImg');
    const layer = document.getElementById('overlayLayer');
    if (!img || !layer) return;

    const imageSize = currentData.image_size || {};
    const origW = imageSize.width || 0;
    const origH = imageSize.height || 0;
    if (!origW || !origH) return;

    const dispW = img.offsetWidth;
    const dispH = img.offsetHeight;
    const scaleX = dispW / origW;
    const scaleY = dispH / origH;

    layer.innerHTML = '';
    layer.style.pointerEvents = 'auto';

    let globalIdx = 0;
    for (const part of (currentData.aliyun_result?.parts || [])) {
        for (const q of (part.questions || [])) {
            const idx = globalIdx++;
            const pos = q.position;
            if (!pos || !pos.width) continue;

            const left = pos.x * scaleX;
            const top = pos.y * scaleY;
            const width = pos.width * scaleX;
            const height = pos.height * scaleY;

            const box = document.createElement('div');
            box.className = 'img-overlay-box';
            box.dataset.questionId = q.id;
            box.style.cssText = `
                position: absolute;
                left: ${left}px; top: ${top}px;
                width: ${width}px; height: ${height}px;
                border: 2px solid transparent;
                border-radius: 3px;
                background: transparent;
                cursor: pointer;
                transition: background 0.2s, border-color 0.2s;
                box-sizing: border-box;
            `;

            // 序号标签
            const label = document.createElement('span');
            label.textContent = idx + 1;
            label.style.cssText = `
                position: absolute;
                top: -1px; left: -1px;
                background: #4f8ef7;
                color: #fff;
                font-size: 11px;
                font-weight: bold;
                padding: 1px 5px;
                border-radius: 2px;
                opacity: 0;
                transition: opacity 0.2s;
            `;
            box.appendChild(label);

            box.addEventListener('click', () => activateQuestion(q.id));
            layer.appendChild(box);
        }
    }
}

// 激活指定题目（左右同时高亮）
function activateQuestion(questionId) {
    // 清除旧高亮
    document.querySelectorAll('.img-overlay-box').forEach(b => {
        b.style.background = 'transparent';
        b.style.borderColor = 'transparent';
        b.querySelector('span').style.opacity = '0';
    });
    document.querySelectorAll('.question-item').forEach(el => {
        el.classList.remove('highlighted');
    });

    // 高亮 overlay
    const box = document.querySelector(`.img-overlay-box[data-question-id="${questionId}"]`);
    if (box) {
        box.style.background = 'rgba(79,142,247,0.12)';
        box.style.borderColor = '#4f8ef7';
        box.querySelector('span').style.opacity = '1';
    }

    // 高亮右侧题目并滚动到可见区
    const item = document.querySelector(`.question-item[data-question-id="${questionId}"]`);
    if (item) {
        item.classList.add('highlighted');
        item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// 更新结果显示
function updateResultView() {
    if (!currentData) return;

    const mode = currentViewMode;

    // 原始 JSON 两个阶段都用同一个数据
    if (mode === 'raw_json') {
        resultContainer.className = 'content-area json-view';
        resultContainer.innerHTML = renderJSON(currentData.raw_ocr_result);
        return;
    }

    // 根据当前阶段选择数据源
    if (currentStage === 'glm') {
        // 使用 GLM 优化后的结果
        if (mode === 'markdown') {
            const content = currentData.glm_markdown || '';
            resultContainer.className = 'content-area markdown-view';
            resultContainer.innerHTML = renderMarkdown(content);
        } else {
            resultContainer.className = 'content-area json-view';
            resultContainer.innerHTML = renderJSON(currentData.glm_result);
        }
    } else {
        // 使用阿里云原始结果
        if (mode === 'markdown') {
            const content = currentData.markdown || '';
            resultContainer.className = 'content-area markdown-view';
            resultContainer.innerHTML = renderMarkdown(content);

            // 恢复刚才已经单题优化过的 HTML
            if (currentData.single_optimizations) {
                for (const qId of Object.keys(currentData.single_optimizations)) {
                    const qDiv = resultContainer.querySelector(`.question-item[data-question-id="${qId}"]`);
                    if (qDiv) {
                        qDiv.outerHTML = currentData.single_optimizations[qId].markdown_snippet;
                    }
                }
            }
        } else {
            resultContainer.className = 'content-area json-view';
            resultContainer.innerHTML = renderJSON(currentData.aliyun_result);
        }
    }

    // 添加题目悬停联动效果
    if (mode === 'markdown') {
        renderLatex(resultContainer);
        addQuestionHoverEffect();
    }
}

// 渲染 Markdown
function renderMarkdown(content) {
    if (!content) return '';
    if (typeof marked === 'undefined') return formatMarkdown(content);
    return marked.parse(content);
}

// 对容器内的 $...$ 和 $$...$$ 做 KaTeX 公式渲染
function renderLatex(el) {
    if (!el || typeof renderMathInElement === 'undefined') return;
    renderMathInElement(el, {
        delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
        ],
        throwOnError: false,
    });
}

// 渲染可折叠的 JSON
function renderJSON(obj, level = 0) {
    try {
        // 限制最大深度,防止递归过深
        if (level > 10) {
            return '<span class="json-string">"[深度超限]"</span>';
        }

        if (obj === null) return '<span class="json-null">null</span>';
        if (obj === undefined) return '<span class="json-undefined">undefined</span>';

        const type = typeof obj;

        if (type === 'string') {
            return `<span class="json-string">"${escapeHtml(obj)}"</span>`;
        }
        if (type === 'number') {
            return `<span class="json-number">${obj}</span>`;
        }
        if (type === 'boolean') {
            return `<span class="json-boolean">${obj}</span>`;
        }

        if (Array.isArray(obj)) {
            if (obj.length === 0) return '<span class="json-bracket">[]</span>';

            const id = 'json-' + Math.random().toString(36).substr(2, 9);
            const indent = '  '.repeat(level);
            const childIndent = '  '.repeat(level + 1);

            let html = `<span class="json-bracket">[</span>`;
            html += `<span class="json-toggle" onclick="toggleJSON('${id}')">▼</span>`;
            html += `<div id="${id}" class="json-collapsible">`;

            const items = obj;

            items.forEach((item, i) => {
                html += `\n${childIndent}${renderJSON(item, level + 1)}`;
                if (i < items.length - 1) html += '<span class="json-comma">,</span>';
            });

            html += `\n${indent}</div><span class="json-bracket">]</span>`;
            return html;
        }

        if (type === 'object') {
            const keys = Object.keys(obj);
            if (keys.length === 0) return '<span class="json-bracket">{}</span>';

            const id = 'json-' + Math.random().toString(36).substr(2, 9);
            const indent = '  '.repeat(level);
            const childIndent = '  '.repeat(level + 1);

            let html = `<span class="json-bracket">{</span>`;
            html += `<span class="json-toggle" onclick="toggleJSON('${id}')">▼</span>`;
            html += `<div id="${id}" class="json-collapsible">`;

            const displayKeys = keys;

            displayKeys.forEach((key, i) => {
                html += `\n${childIndent}<span class="json-key">"${escapeHtml(key)}"</span>: `;
                html += renderJSON(obj[key], level + 1);
                if (i < displayKeys.length - 1) html += '<span class="json-comma">,</span>';
            });

            html += `\n${indent}</div><span class="json-bracket">}</span>`;
            return html;
        }

        return String(obj);
    } catch (error) {
        console.error('renderJSON error:', error);
        return `<span class="json-string">"[渲染错误: ${error.message}]"</span>`;
    }
}

// 切换 JSON 折叠
function toggleJSON(id) {
    const element = document.getElementById(id);
    const toggle = element.previousElementSibling;

    if (element.style.display === 'none') {
        element.style.display = 'inline';
        toggle.textContent = '▼';
    } else {
        element.style.display = 'none';
        toggle.textContent = '▶';
    }
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 添加题目悬停联动效果
function addQuestionHoverEffect() {
    const questionItems = resultContainer.querySelectorAll('.question-item');

    questionItems.forEach(item => {
        item.addEventListener('mouseenter', function () {
            const questionId = this.getAttribute('data-question-id');
            activateQuestion(questionId);
        });

        item.addEventListener('mouseleave', function () {
            // 只取消高亮，保留最后一次 click 的激活状态
            document.querySelectorAll('.question-item').forEach(el => el.classList.remove('highlighted'));
            document.querySelectorAll('.img-overlay-box').forEach(b => {
                b.style.background = 'transparent';
                b.style.borderColor = 'transparent';
                b.querySelector('span').style.opacity = '0';
            });
        });
    });
}

// 格式化 Markdown（如果未加载 marked.js 时备用）
function formatMarkdown(markdown) {
    if (!markdown) return '';
    return markdown
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

// 更新状态标签
function updateStatus(elementId, statusClass, text) {
    const element = document.getElementById(elementId);
    element.className = 'status ' + statusClass;
    element.textContent = text;
}

// Loading 控制
function showLoading(text, hint = '') {
    loadingText.textContent = text;
    loadingHint.textContent = hint;
    loading.classList.remove('hidden');
}

function hideLoading() {
    loading.classList.add('hidden');
}

// 页面加载完成
document.addEventListener('DOMContentLoaded', () => {
    console.log('📝 试卷识别 Demo 已加载');
    console.log('API 地址:', API_BASE);
});
// --- 单题优化处理逻辑 ---
async function optimizeSingleQuestion(questionId) {
    if (!currentImagePath || !currentData.aliyun_result) {
        alert("请先上传图片并识别");
        return;
    }

    const qDiv = document.querySelector(`.question-item[data-question-id="${questionId}"]`);
    const btn = qDiv ? qDiv.querySelector('.btn-optimize-single') : null;

    if (btn) {
        btn.innerHTML = `<span class="spinner" style="width:12px;height:12px;border-width:2px;margin:0"></span> 优化中...`;
        btn.disabled = true;
    }

    try {
        const response = await fetch(`${API_BASE}/optimize_single`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_path: currentImagePath,
                question_id: questionId,
                aliyun_result: currentData.aliyun_result
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            if (qDiv) {
                // 保存单题优化数据以便后续切换 Tab 恢复
                currentData.single_optimizations = currentData.single_optimizations || {};
                currentData.single_optimizations[questionId] = {
                    markdown_snippet: data.markdown_snippet,
                    optimized_json: data.optimized_json
                };

                // 同步给 JSON 源数据挂上优化后结构，以便能在右侧“解析JSON”视图看到
                if (currentData.aliyun_result && currentData.aliyun_result.parts) {
                    currentData.aliyun_result.parts.forEach(part => {
                        const q = (part.questions || []).find(q => q.id === questionId);
                        if (q) {
                            q.glm_optimized = data.optimized_json;
                        }
                    });
                }

                // 将后端返回的 HTML 标记文本片段使用 marked 解析成 DOM
                qDiv.outerHTML = data.markdown_snippet;


                // 给新插入的 DOM 节点重新绑定鼠标事件（因为外层 outerHTML 被整体替换）
                addQuestionHoverEffect();

                // 单独重新渲染本题的 LaTeX
                const newDiv = document.querySelector(`.question-item[data-question-id="${questionId}"]`);
                if (window.renderMathInElement && newDiv) {
                    window.renderMathInElement(newDiv, {
                        delimiters: [
                            { left: "$$", right: "$$", display: true },
                            { left: "$", right: "$", display: false }
                        ],
                        throwOnError: false
                    });
                }
            }
        } else {
            alert('单题优化失败: ' + data.message);
            if (btn) {
                btn.innerHTML = `🪄 智能修复此题`;
                btn.disabled = false;
            }
        }
    } catch (e) {
        console.error("单题优化出错: ", e);
        alert('请求出错，请查看控制台');
        if (btn) {
            btn.innerHTML = `🪄 智能修复此题`;
            btn.disabled = false;
        }
    }
}
