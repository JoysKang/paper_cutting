#!/bin/bash

echo "=================================="
echo "试卷识别 Demo 启动脚本"
echo "=================================="

# 检查环境变量
if [ -z "$ALIYUN_ACCESS_KEY_ID" ]; then
    echo "⚠️  警告: ALIYUN_ACCESS_KEY_ID 未设置"
fi

if [ -z "$ALIYUN_ACCESS_KEY_SECRET" ]; then
    echo "⚠️  警告: ALIYUN_ACCESS_KEY_SECRET 未设置"
fi

if [ -z "$GLM_API_KEY" ]; then
    echo "⚠️  警告: GLM_API_KEY 未设置"
fi

# 创建必要的目录
mkdir -p uploads
mkdir -p output

# 检查依赖
echo ""
echo "检查 Python 依赖..."
pip list | grep -q flask
if [ $? -ne 0 ]; then
    echo "❌ Flask 未安装"
    echo "   运行: pip install -r backend/requirements.txt"
    exit 1
fi

echo "✓ 依赖检查通过"
echo ""

# 启动服务
echo "🚀 启动后端服务..."
echo "   访问地址: http://localhost:5000"
echo "=================================="
echo ""

cd backend
python app.py
