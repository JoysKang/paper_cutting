# 试卷识别 Demo（简化版）

整合阿里云读光 OCR 和 GLM 智能优化的试卷识别系统演示。

## 🎯 核心理念

- **阿里云读光**：快速识别，提取题目结构和坐标
- **GLM 优化**：智能优化，修正错误，优化结构
- **简洁设计**：最小化依赖，专注核心功能

## 📁 项目结构

```
paper_cutting_v2/
├── backend/
│   ├── app.py              # Flask 后端服务
│   ├── aliyun_paper.py     # 阿里云 OCR 模块
│   ├── glm_optimizer.py    # GLM 优化器（简化版）
│   └── requirements.txt    # Python 依赖
├── frontend/
│   ├── index.html          # 前端页面
│   └── static/
│       ├── style.css       # 样式文件
│       └── app.js          # 前端逻辑
├── uploads/                # 上传文件目录
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 阿里云密钥
export ALIYUN_ACCESS_KEY_ID="your_aliyun_key_id"
export ALIYUN_ACCESS_KEY_SECRET="your_aliyun_key_secret"

# GLM API Key
export GLM_API_KEY="your_glm_api_key"
```

### 3. 启动服务

```bash
# 方式 1：使用启动脚本
./start.sh

# 方式 2：手动启动
cd backend
python app.py
```

### 4. 访问页面

打开浏览器访问：`http://localhost:5000`

## 📖 使用说明

### 基本流程

1. **上传图片** → 选择试卷图片 → 点击"上传识别"
2. **查看结果** → 左侧显示原图，右侧显示识别结果
3. **GLM 优化**（可选）→ 点击"GLM 优化"按钮
4. **对比结果** → 切换 Markdown/JSON 格式查看

### 功能说明

#### 阿里云读光识别
- 快速识别（5-10秒）
- 提取题目结构
- 识别选项和答案区域
- 提供精确坐标信息

#### GLM 智能优化
- 修正识别错误
- 优化题目结构
- 拆分复杂题目
- 统一格式规范

## 🔧 技术栈

### 后端
- **Flask**：轻量级 Web 框架
- **阿里云读光 OCR**：试卷识别 API
- **智谱 GLM**：智能优化

### 前端
- **原生 HTML/CSS/JS**：无框架依赖
- **响应式设计**：支持不同屏幕

## 📊 API 接口

### 1. 上传识别

```
POST /api/upload
Content-Type: multipart/form-data

参数：
- file: 图片文件

返回：
{
  "status": "success",
  "image_path": "...",
  "aliyun_result": {...},
  "markdown": "...",
  "json": {...}
}
```

### 2. GLM 优化

```
POST /api/optimize
Content-Type: application/json

参数：
{
  "image_path": "...",
  "aliyun_result": {...}
}

返回：
{
  "status": "success",
  "glm_result": {...},
  "markdown": "...",
  "json": {...}
}
```

## ⚙️ 核心模块说明

### aliyun_paper.py
- 阿里云 OCR 封装
- 题目解析和结构化
- 坐标信息提取

### glm_optimizer.py（简化版）
- 专注于优化阿里云结果
- 不做完整 OCR 流程
- 使用统一的优化提示词
- 无需复杂的提示词系统

### app.py
- Flask 路由和 API
- 文件上传处理
- 结果格式转换

## ⚠️ 注意事项

1. **环境变量**：必须配置阿里云和 GLM 的 API 密钥
2. **网络连接**：需要能访问阿里云和 GLM 的 API
3. **文件大小**：建议上传文件小于 10MB
4. **处理时间**：
   - 阿里云识别：5-10 秒
   - GLM 优化：10-30 秒（简化版更快）

## 🆚 与完整版的区别

| 特性 | 完整版 | Demo 简化版 |
|------|--------|------------|
| GLM 功能 | 完整 OCR + 结构化 | 仅优化阿里云结果 |
| 提示词系统 | 多学段多学科 | 统一优化提示词 |
| 处理时间 | 30-60 秒 | 10-30 秒 |
| 依赖复杂度 | 高 | 低 |
| 适用场景 | 生产环境 | 功能验证 |

## 🐛 常见问题

### 问题 1：模块导入失败

```
ModuleNotFoundError: No module named 'zhipuai'
```

**解决**：安装依赖 `pip install zhipuai`

### 问题 2：环境变量未设置

```
⚠️ 阿里云密钥未设置
```

**解决**：检查环境变量是否正确设置

### 问题 3：GLM 优化失败

**可能原因**：
- API Key 错误
- 网络连接问题
- 返回结果格式错误

**解决**：查看后端日志，检查详细错误信息

## 📝 开发说明

### 添加新功能

1. **后端**：在 `backend/app.py` 中添加新路由
2. **前端**：在 `frontend/static/app.js` 中添加新函数

### 调试模式

后端默认开启 Debug 模式，修改代码后会自动重启。

### 日志查看

后端会在控制台输出详细日志：
- 文件上传信息
- OCR 识别进度
- GLM 优化进度
- 错误信息

## 📄 许可证

MIT License
