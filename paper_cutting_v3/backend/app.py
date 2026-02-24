#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
试卷识别 Demo - 后端服务
整合阿里云读光 OCR 和 GLM 优化
"""

import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import base64
import io
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    pass


# 导入本地模块
from aliyun_paper import AliyunPaperOCR
from glm_optimizer import GLMOptimizer
from dotenv import load_dotenv

# 配置路径
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')

FRONTEND_DIR = BASE_DIR / 'frontend'
STATIC_DIR = FRONTEND_DIR / 'static'
UPLOAD_FOLDER = BASE_DIR / 'uploads'
OUTPUT_FOLDER = BASE_DIR / 'output'

app = Flask(__name__, 
            static_folder=str(STATIC_DIR),
            static_url_path='/static')
CORS(app)

# 确保目录存在
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 初始化处理器
aliyun_ocr = None
glm_optimizer = None

def init_processors():
    """初始化 OCR 处理器"""
    global aliyun_ocr, glm_optimizer
    
    # 阿里云 OCR
    aliyun_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
    aliyun_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
    
    if aliyun_key_id and aliyun_key_secret:
        aliyun_ocr = AliyunPaperOCR(aliyun_key_id, aliyun_key_secret)
        print("✓ 阿里云 OCR 初始化成功")
    else:
        print("⚠️  阿里云密钥未设置")
    
    # GLM 优化器
    glm_api_key = os.getenv('GLM_API_KEY')
    if glm_api_key:
        glm_optimizer = GLMOptimizer(api_key=glm_api_key)
        print("✓ GLM 优化器初始化成功")
    else:
        print("⚠️  GLM API Key 未设置")


@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/api/upload', methods=['POST'])
def upload_image():
    """上传图片并调用阿里云识别"""
    if not aliyun_ocr:
        return jsonify({
            'status': 'error',
            'message': '阿里云 OCR 未初始化，请检查环境变量'
        }), 500
    
    if 'file' not in request.files:
        return jsonify({
            'status': 'error',
            'message': '未找到文件'
        }), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            'status': 'error',
            'message': '文件名为空'
        }), 400
    
    try:
        # 使用原始文件名(去掉扩展名)作为目录名
        original_filename = Path(file.filename).stem
        
        # 为这个图片创建独立的输出目录
        image_output_dir = OUTPUT_FOLDER / original_filename
        image_output_dir.mkdir(exist_ok=True, parents=True)
        
        # 保存上传的图片到输出目录
        filepath = image_output_dir / file.filename
        file.save(filepath)
        
        print(f"📁 文件已保存: {filepath}")
        
        # 创建切图子目录
        images_dir = image_output_dir / 'images'
        images_dir.mkdir(exist_ok=True)
        
        # 调用阿里云 OCR
        print("🔍 开始阿里云识别...")
        ocr_result = aliyun_ocr.recognize_paper(
            image_path=str(filepath),
            extract_images=False  # 先不切图,后面手动处理
        )
        
        # 解析 Data 字段(如果是字符串)
        if 'Data' in ocr_result and isinstance(ocr_result['Data'], str):
            import json as json_lib
            ocr_result['Data'] = json_lib.loads(ocr_result['Data'])
        
        # 保存阿里云原始 JSON 到图片目录(完整格式化)
        aly_json_path = image_output_dir / f"{original_filename}_aly.json"
        with open(aly_json_path, 'w', encoding='utf-8') as f:
            json.dump(ocr_result, f, ensure_ascii=False, indent=2)
        print(f"💾 阿里云结果已保存: {aly_json_path}")
        
        # 手动切图:只切 subject_pattern 类型的图片,并建立坐标到索引的映射
        from PIL import Image
        img = Image.open(filepath)
        figure_list = ocr_result.get('Data', {}).get('figure', [])
        
        # 收集所有 subject_pattern 类型的图片及其坐标
        pattern_map = {}  # 坐标 -> 索引
        pattern_index = 1
        
        for fig in figure_list:
            if fig.get('type') == 'subject_pattern':
                points = fig.get('points', [])
                if len(points) >= 4:
                    # 计算边界框
                    xs = [p['x'] for p in points]
                    ys = [p['y'] for p in points]
                    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                    
                    # 切图
                    cropped = img.crop((x1, y1, x2, y2))
                    output_path = images_dir / f"pattern_{pattern_index}.png"
                    cropped.save(output_path)
                    
                    # 记录坐标到索引的映射 (使用中心点作为key)
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    pattern_map[(center_x, center_y)] = pattern_index
                    
                    pattern_index += 1
        
        print(f"🖼️  切图完成: {pattern_index - 1} 张配图")
        
        # 解析结果
        parsed_result = aliyun_ocr.parse_questions(ocr_result)
        
        # 为每道题匹配图片索引 (从原始 JSON 中获取 figure_list)
        data_obj = ocr_result.get('Data', {})
        part_info = data_obj.get('part_info', [])
        
        for part_idx, part_data in enumerate(part_info):
            if part_idx >= len(parsed_result.get('parts', [])):
                continue
                
            parsed_part = parsed_result['parts'][part_idx]
            subject_list = part_data.get('subject_list', [])
            
            for subj_idx, subject_data in enumerate(subject_list):
                if subj_idx >= len(parsed_part.get('questions', [])):
                    continue
                    
                q = parsed_part['questions'][subj_idx]
                q['figures'] = []
                
                # 获取该题目的 figure_list
                fig_list = subject_data.get('figure_list', [])
                
                for fig_coords in fig_list:
                    if isinstance(fig_coords, list) and len(fig_coords) >= 4:
                        # 计算图片中心点
                        xs = [p['x'] for p in fig_coords]
                        ys = [p['y'] for p in fig_coords]
                        center_x = sum(xs) / len(xs)
                        center_y = sum(ys) / len(ys)
                        
                        # 在 pattern_map 中查找最接近的图片
                        min_dist = float('inf')
                        best_index = None
                        
                        for (px, py), idx in pattern_map.items():
                            dist = ((center_x - px) ** 2 + (center_y - py) ** 2) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                best_index = idx
                        
                        if best_index and min_dist < 100:  # 距离阈值
                            # 同时存 index 和 bbox，供前端联合高亮用
                            q['figures'].append({
                                'index': best_index,
                                'bbox': {
                                    'x': min(xs), 'y': min(ys),
                                    'width': max(xs) - min(xs),
                                    'height': max(ys) - min(ys),
                                }
                            })
        
        print(f"✓ 图片匹配完成")
        
        # 转换为 Markdown (传入图片目录信息)
        markdown = convert_to_markdown(
            parsed_result, 
            image_output_dir=images_dir,
            original_filename=original_filename
        )
        
        print("✓ 阿里云识别完成")
        
        # 提取原图尺寸（供前端坐标换算）
        data_obj_for_size = ocr_result.get('Data', {})
        image_size = {
            'width': data_obj_for_size.get('width', 0),
            'height': data_obj_for_size.get('height', 0),
        }
        
        return jsonify({
            'status': 'success',
            'image_path': str(filepath),
            'image_filename': file.filename,
            'original_filename': original_filename,
            'image_output_dir': str(images_dir),
            'aliyun_result': parsed_result,
            'raw_ocr_result': ocr_result,
            'image_size': image_size,
            'markdown': markdown,
            'json': parsed_result
        })
    
    except Exception as e:
        print(f"❌ 识别失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/optimize', methods=['POST'])
def optimize_with_glm():
    """使用 GLM 优化结果"""
    if not glm_optimizer:
        return jsonify({
            'status': 'error',
            'message': 'GLM 优化器未初始化，请检查环境变量'
        }), 500
    
    try:
        data = request.json
        image_path = data.get('image_path')
        aliyun_result = data['aliyun_result']
        original_filename = data.get('original_filename', 'result')
        
        print(f"🤖 开始 GLM 优化...")
        
        # 调用 GLM 优化
        glm_result = glm_optimizer.optimize(
            aliyun_result=aliyun_result,
            image_url=image_path
        )
        
        # 保存 GLM 优化结果 JSON 到图片目录
        image_output_dir = OUTPUT_FOLDER / original_filename
        glm_json_path = image_output_dir / f"{original_filename}_glm.json"
        with open(glm_json_path, 'w', encoding='utf-8') as f:
            json.dump(glm_result, f, ensure_ascii=False, indent=2)
        print(f"💾 GLM 结果已保存: {glm_json_path}")
        
        # 转换为 Markdown（现在 glm_result 拥有和阿里云原始一致的整体结构，只是更新了相关属性）
        glm_markdown = convert_to_markdown(
            glm_result, 
            image_output_dir=image_output_dir, 
            original_filename=original_filename
        )

        print("✓ GLM 优化完成")
        
        return jsonify({
            'status': 'success',
            'glm_result': glm_result,
            'markdown': glm_markdown,
            'json': glm_result
        })
    
    except Exception as e:
        print(f"❌ 优化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/optimize_single', methods=['POST'])
def optimize_single_question():
    """使用 GLM 优化单道题"""
    if not glm_optimizer:
        return jsonify({'status': 'error', 'message': 'GLM 优化器未初始化'}), 500
    
    try:
        data = request.json
        image_path = data.get('image_path')
        question_id = data.get('question_id')
        aliyun_result = data.get('aliyun_result')
        
        # 寻找对应的 question
        target_q = None
        for part in aliyun_result.get('parts', []):
            for q in part.get('questions', []):
                if q.get('id') == question_id:
                    target_q = q
                    break
            if target_q:
                break
                
        if not target_q:
            return jsonify({'status': 'error', 'message': '找不到对应的题目数据'}), 404
            
        print(f"🤖 开始单题 GLM 优化: {question_id}")
        
        img_b64 = None
        if image_path and os.path.exists(image_path) and target_q.get('position'):
            # 使用 PIL 根据 position 裁切指定题目的图片区域
            try:
                img = Image.open(image_path)
                pos = target_q['position']
                # box: (left, upper, right, lower)
                box = (pos['x'] - 10, pos['y'] - 10, pos['x'] + pos['width'] + 10, pos['y'] + pos['height'] + 10)
                box = (max(0, box[0]), max(0, box[1]), min(img.width, box[2]), min(img.height, box[3]))
                cropped = img.crop(box)
                
                buffer = io.BytesIO()
                # 统一转为 RGB 保存 JPEG 以优化体积，或保持 PNG
                if cropped.mode != 'RGB':
                    cropped = cropped.convert('RGB')
                cropped.save(buffer, format="JPEG")
                img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"⚠️ 图像裁切失败，将以纯文本模式优化本题: {e}")
        
        # 单题优化
        optimized_json = glm_optimizer.optimize_single(target_q, image_b64=img_b64)
        # 把优化结果合并进 target_q，这样渲染时能拿到最新的 text/options
        if optimized_json and not optimized_json.get('error'):
            target_q['glm_optimized'] = optimized_json
            if optimized_json.get('prompt'):
                target_q['type_name'] = optimized_json['prompt']
            target_q['text'] = (optimized_json.get('content') or target_q.get('text', ''))
            if optimized_json.get('opts'):
                target_q['options'] = [
                    {"option": o.get("id", ""), "text": o.get("txt", "")}
                    for o in optimized_json.get('opts', [])
                ]
        
        # 渲染单题 HTML 片段
        image_output_dir = OUTPUT_FOLDER / data.get('original_filename', 'result')
        markdown_snippet = render_single_question_html(
            target_q,
            image_output_dir=image_output_dir,
            original_filename=data.get('original_filename', 'result'),
            is_optimized=True
        )

        
        return jsonify({
            'status': 'success',
            'question_id': question_id,
            'markdown_snippet': markdown_snippet,
            'optimized_json': optimized_json
        })
        
    except Exception as e:
        print(f"❌ 单题优化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


def render_single_question_html(q: dict, image_output_dir=None, original_filename=None, is_optimized=False):
    """提取的通用单题 HTML 渲染逻辑片段"""
    lines = []
    q_id = q.get('id', '')
    
    css_class = 'question-item optim-highlight' if is_optimized else 'question-item'
    lines.append(f'<div class="{css_class}" data-question-id="{q_id}">')
    
    lines.append(f'<div class="q-actions"><button class="btn-optimize-single" onclick="optimizeSingleQuestion(\'{q_id}\')">✨ 重新优化</button></div>')
    
    type_name = q.get('type_name')
    if type_name:
        lines.append(f"[{type_name}] {q.get('text', '')}\n")
    else:
        lines.append(f"{q.get('text', '')}\n")
    
    figures = q.get('figures', [])
    if figures and image_output_dir and original_filename:
        lines.append('<div class="question-figures">')
        for fig_info in figures:
            fig_index = fig_info.get('index', 0)
            img_url = f"/output/{original_filename}/images/pattern_{fig_index}.png"
            lines.append(f'<img src="{img_url}" alt="配图{fig_index}" class="question-image" />')
        lines.append('</div>\n')
    
    if q.get('options'):
        lines.append('<div class="options">')
        for opt in q['options']:
            lines.append(f"{opt.get('option', '')}. {opt.get('text', '')}")
        lines.append('</div>\n')

    # 处理单题修复中附带的子题结构
    glm_opt = q.get('glm_optimized', {})
    if glm_opt.get('subqs'):
        lines.append('<div class="subquestions">')
        for subq in glm_opt['subqs']:
            lines.append(f"  ({subq.get('no', '')}) {subq.get('content', '')}")
        lines.append('</div>\n')
        
    lines.append('</div>\n')
    
    result = "\n".join(lines)
    result = re.sub(r'\$\$(.+?)\$\$', r'$\1$', result)
    return result

@app.route('/output/<path:filepath>')
def serve_output(filepath):
    """返回 output 目录中的文件"""
    return send_from_directory(OUTPUT_FOLDER, filepath)



def convert_to_markdown(parsed_result, image_output_dir=None, original_filename=None):
    """将阿里云结果转为 Markdown"""
    lines = []
    
    question_number = 1  # 全局题号计数器
    
    for part in parsed_result.get('parts', []):
        if part['title']:  # 只有非空标题才显示
            lines.append(f"## {part['title']}\n")
        
        for q in part.get('questions', []):
            snippet = render_single_question_html(
                q, 
                image_output_dir=image_output_dir, 
                original_filename=original_filename
            )
            lines.append(snippet)
            question_number += 1  # 递增题号
    
    result = "\n".join(lines)
    return result


def convert_glm_to_markdown(glm_result):
    """将 GLM 结果转为 Markdown"""
    lines = []
    
    for section in glm_result.get('sections', []):
        lines.append(f"## {section.get('no', '')}、{section.get('title', '')}\n")
        
        if section.get('desc'):
            lines.append(f"*{section['desc']}*\n")
        
        for q in section.get('qs', []):
            # 添加题目 ID (用于前端联动)
            q_no = q.get('no', '')
            lines.append(f'<div class="question-item" data-question-id="{q_no}">')
            
            prompt = q.get('prompt', '')
            content = q.get('content', '')
            
            # 题干
            if prompt:
                lines.append(f"[{prompt}] {content}\n")
            else:
                lines.append(f"{content}\n")
            
            # 选项 (单独显示)
            if q.get('opts'):
                lines.append('<div class="options">')
                for opt in q['opts']:
                    lines.append(f"{opt['id']}. {opt['txt']}")
                lines.append('</div>\n')
            
            # 子题
            if q.get('subqs'):
                lines.append('<div class="subquestions">')
                for subq in q['subqs']:
                    lines.append(f"  ({subq.get('no', '')}) {subq.get('content', '')}")
                lines.append('</div>\n')
            
            lines.append('</div>\n')
    
    return "\n".join(lines)


if __name__ == '__main__':
    print("=" * 60)
    print("试卷识别 Demo - 后端服务")
    print("=" * 60)
    
    # 初始化处理器
    init_processors()
    
    print("\n🚀 服务启动中...")
    print("   访问地址: http://localhost:8000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=8000)
