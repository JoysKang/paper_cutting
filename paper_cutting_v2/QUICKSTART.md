# 快速启动指南

## 📦 安装依赖

```bash
# 1. 进入后端目录
cd backend

# 2. 安装 Flask 依赖
pip install flask flask-cors

# 3. 安装阿里云 OCR SDK
pip install alibabacloud-ocr-api20210707 alibabacloud-tea-openapi

# 4. 安装图片处理库
pip install Pillow

# 5. 安装 GLM SDK（如果需要优化功能）
# 注意：需要从父项目的 paper_cutting 目录获取 zai 模块
```

## 🔑 配置密钥

### 方式 1：环境变量（推荐）

```bash
export ALIYUN_ACCESS_KEY_ID="你的阿里云AccessKeyId"
export ALIYUN_ACCESS_KEY_SECRET="你的阿里云AccessKeySecret"
export GLM_API_KEY="你的GLM_API_Key"
```

### 方式 2：.env 文件

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，填入真实密钥
nano .env
```

## 🚀 启动服务

### 方式 1：使用启动脚本

```bash
./start.sh
```

### 方式 2：手动启动

```bash
cd backend
python app.py
```

## 🌐 访问页面

打开浏览器访问：**http://localhost:5000**

## 📝 使用流程

1. **上传图片**
   - 点击"选择文件"
   - 选择试卷图片
   - 点击"上传识别"

2. **查看结果**
   - 左侧：原始图片
   - 右侧：识别结果（可切换 Markdown/JSON）

3. **GLM 优化**（可选）
   - 选择学段和科目
   - 点击"GLM 优化"
   - 等待 30-60 秒

## ⚡ 快速测试

```bash
# 1. 设置环境变量
export ALIYUN_ACCESS_KEY_ID="your_key"
export ALIYUN_ACCESS_KEY_SECRET="your_secret"
export GLM_API_KEY="your_glm_key"

# 2. 启动服务
cd backend && python app.py

# 3. 打开浏览器
open http://localhost:5000
```

## 🐛 故障排查

### 问题 1：模块导入失败

```
ModuleNotFoundError: No module named 'aliyun_paper_ocr'
```

**解决**：确保项目结构正确，`notebook/api` 目录存在

### 问题 2：环境变量未设置

```
⚠️ 阿里云密钥未设置
```

**解决**：检查环境变量是否正确设置

### 问题 3：端口被占用

```
Address already in use
```

**解决**：修改 `app.py` 中的端口号，或关闭占用 5000 端口的程序

## 📞 获取帮助

如有问题，请查看完整的 [README.md](README.md) 文档。
