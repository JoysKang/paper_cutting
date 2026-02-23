#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLM 优化器 - 用于优化阿里云读光的识别结果
简化版本，只负责优化，不做完整的 OCR 流程
"""
import json
import base64
import os
import io
import json_repair
from typing import Dict
from PIL import Image
import concurrent.futures



try:
    from zhipuai import ZhipuAI
except ImportError:
    print("⚠️  需要安装 zhipuai: pip install zhipuai")
    ZhipuAI = None


class GLMOptimizer:
    """GLM 优化器 - 优化阿里云识别结果"""
    
    def __init__(self, api_key: str):
        """
        初始化 GLM 客户端
        
        Args:
            api_key: GLM API Key
        """
        if not ZhipuAI:
            raise ImportError("请先安装 zhipuai: pip install zhipuai")
        
        self.client = ZhipuAI(api_key=api_key)
        self.text_model = "glm-4-flash"
        self.vision_model = "glm-4.6v-flash"  # 支持视觉信息的快速模型
    
    def optimize(self, aliyun_result: Dict, image_url: str | None = None) -> Dict:
        """
        全面优化阿里云识别结果 (通过并发对各小题进行裁剪并执行单题优化以实现最佳多模态视觉修复效果)
        """
        import copy
        merged_result = copy.deepcopy(aliyun_result)
        
        # 预先开启并加载源图像（如果存在）
        source_image = None
        if image_url and os.path.exists(image_url):
            try:
                source_image = Image.open(image_url)
            except Exception as e:
                print(f"⚠️ 图片读取失败，将降级为纯文本模式: {e}")

        # 收集所有题目及对应截图
        tasks = []
        for part_idx, part in enumerate(merged_result.get('parts', [])):
            for q_idx, q in enumerate(part.get('questions', [])):
                img_b64 = None
                if source_image and q.get('position'):
                    try:
                        pos = q['position']
                        box = (pos['x'] - 10, pos['y'] - 10, pos['x'] + pos['width'] + 10, pos['y'] + pos['height'] + 10)
                        box = (max(0, box[0]), max(0, box[1]), min(source_image.width, box[2]), min(source_image.height, box[3]))
                        cropped = source_image.crop(box)
                        
                        buffer = io.BytesIO()
                        if cropped.mode != 'RGB':
                            cropped = cropped.convert('RGB')
                        cropped.save(buffer, format="JPEG")
                        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    except Exception as e:
                        print(f"⚠️ 题目 {q.get('id')} 切图失败: {e}")
                        
                # 将要执行的单题任务封存
                tasks.append((part_idx, q_idx, q, img_b64))
                
        def process_task(task_args):
            p_idx, q_idx, target_q, b64 = task_args
            try:
                # 调用单题优化
                opt_data = self.optimize_single(target_q, image_b64=b64)
                return p_idx, q_idx, opt_data
            except Exception as e:
                print(f"题目 {target_q.get('id')} GLM 优化异常: {e}")
                return p_idx, q_idx, None

        # 并发执行 (最大并行 6，防止极速触发 API 限制)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(process_task, tasks))
            
        # 将并发拉取回来的高质量识别结果融合替换进去
        for p_idx, q_idx, opt_q in results:
            if opt_q:
                q = merged_result['parts'][p_idx]['questions'][q_idx]
                q['glm_optimized'] = opt_q
                
                # 覆盖原题文本
                if opt_q.get('prompt'):
                    q['type_name'] = opt_q['prompt']
                    
                q['text'] = (opt_q.get('content') or q.get('text') or '')

                
                # 覆盖选项
                if opt_q.get('opts'):
                    q['options'] = [
                        {"option": o.get("id", ""), "text": o.get("txt", "")} 
                        for o in opt_q.get('opts', [])
                    ]

        return merged_result

            
    def optimize_single(self, question_data: Dict, image_b64: str | None = None) -> Dict:
        """优化单道题"""
        text_description = self._convert_single_to_text(question_data)
        prompt = self._build_prompt(text_description)
        
        # 对于单题，要求直接返回对应的对象而不是外层数组
        prompt += "\n\n请不要返回 questions 数组，而是仅针对这一题，直接返回一个 JSON 对象，格式如下：\n"
        prompt += '{"id": "此处填入原题的id", "prompt": "如：填空或口算", "content": "洗稿修复后的完整题干内容", "opts": [{"id":"A","txt":"选项"}]}\n'

        if image_b64:
            model_to_use = self.vision_model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "你是一个单题识别优化助手。请仔细对比图片和 OCR 文本，修正文字与排版的错误。\n对于数学公式和特殊占位符（比如括号、下划线、实心或空心圆圈、方框等用于填空或表示运算符号的地方），请务必保留，绝不能因为 OCR 没有识别到就不输出导致算式黏连缺漏。请使用相应的标准 LaTeX 格式（例如 \\\\bigcirc, \\\\square, \\\\underline{\\\\quad} 等）。\n注意！所有包含数字运算和上述符号的地方，必须用一对 `$` 将其包裹为完整的行内公式形式（例如 `$24 \\\\bigcirc 6 = 30$`）。\n\n" + prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_b64
                            }
                        }
                    ]
                }
            ]
        else:
            model_to_use = self.text_model
            messages = [
                {"role": "system", "content": "你是一个单题识别优化助手，负责修正和优化单题 OCR 识别结果。"},
                {"role": "user", "content": prompt}
            ]
            
        try:
            response = self.client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=0.1
            )
            result_text = response.choices[0].message.content
            return self._parse_json(result_text)
        except Exception as e:
            print(f"❌ 单题GLM优化失败: {str(e)}")
            raise

    def _convert_single_to_text(self, q: Dict) -> str:
        """将单道题目转换为文本描述"""
        lines = []
        lines.append(f"**题目 {q.get('id', '')}** ({q.get('type_name', q.get('type', '未知'))})")
        lines.append(f"题干: {q.get('text', '')}")
        if q.get('options'):
            lines.append("选项:")
            for opt in q['options']:
                lines.append(f"  {opt.get('option', '')} {opt.get('text', '')}")
        return "\n".join(lines)
    
    def _convert_to_text(self, aliyun_result: Dict) -> str:
        """将阿里云结果转换为文本描述"""
        lines = []
        
        for part in aliyun_result.get('parts', []):
            lines.append(f"## {part['title']}")
            lines.append("")
            
            for q in part.get('questions', []):
                lines.append(f"**题目 {q['id']}** ({q['type']})")
                lines.append(f"题干: {q['text']}")
                
                if q.get('options'):
                    lines.append("选项:")
                    for opt in q['options']:
                        lines.append(f"  {opt['option']} {opt['text']}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def _build_prompt(self, text_description: str) -> str:
        """构建优化提示词"""
        return f"""请优化以下试卷 OCR 识别结果：

{text_description}

请按照以下要求优化：

1. **修正识别错误**
   - 对比原图修正明显的文字、公式识别错误和排版缺漏。
   - 极其关键：对于原图中有“占位符”（如供学生填运算符号的圆圈、方框，或填答案的括号、下划线）的地方，必须使用对应的 LaTeX 符号（如 `\\\\bigcirc`、`\\\\square`、`(\\\\quad)`）精确占位。
   - 所有的数学独立字母、算式（包括上述带圆圈的填空算式），**务必使用成对的 `$` 符号严格包裹作为行内公式**（例如：原本连在一起是 24O6=30，应修复并输出为 `$24 \\\\bigcirc 6 = 30$`）。

2. **优化题目结构**
   - 将这道题目进一步拆解为：题目要求语(prompt)、纯粹的题目内容(content)
   - 极其关键：必须把题干中的“选项文本”给剔除干净！选项的内容请严格放在 `opts` 数组里，**绝对不要残留或重复出现在题干 `content` 里面！**
   - 如果一道题包含多个小问，拆分为 subqs 数组

3. **输出格式**
   返回 JSON 格式，务必保证只返回一个扁平的 `questions` 结构。**每一项的 `"id"` 必须严格保留原文本中的题号 ID (例如"0-1", "1-2"等)，不要自己重新编序号**：
   ```json
   {{
     "questions": [
       {{
         "id": "1-1",
         "prompt": "题目要求（如：口算、填空等）",
         "content": "题目洗稿后的高品质内容",
         "opts": [
           {{"id": "A", "txt": "选项内容"}}
         ],
         "subqs": [
           {{"no": "1", "content": "子题内容"}}
         ]
       }}
     ]
   }}
   ```

4. **注意事项**
   - **千万不要丢失或修改原题的 `"id"` 值，否则无法将修复结果匹配合并回去！**
   - 对于不需要大幅修改的题目，也要同样返回原 id 以及 content，保持格式一致。
"""

    def _merge_results(self, original_result: Dict, glm_data: Dict) -> Dict:
        """将 GLM 修复的结果文本合入原始的阿里云 JSON 结构中"""
        import copy
        merged = copy.deepcopy(original_result)
        if not glm_data or not isinstance(glm_data, dict) or 'questions' not in glm_data:
            return merged
        
        q_map = {str(q.get('id')): q for q in glm_data.get('questions', []) if q.get('id')}
        
        for part in merged.get('parts', []):
            for q in part.get('questions', []):
                q_id = str(q.get('id', ''))
                if q_id in q_map:
                    opt_q = q_map[q_id]
                    # 更新原题的 GLM 洗稿标记
                    q['glm_optimized'] = opt_q
                    
                    # 用 GLM 的 content 去覆盖原题的 text
                    if opt_q.get('prompt'):
                        q['type_name'] = opt_q['prompt']
                        
                    q['text'] = (opt_q.get('content') or q.get('text') or '')
                    
                    # 覆盖选项
                    if opt_q.get('opts'):
                        q['options'] = [
                            {"option": o.get("id", ""), "text": o.get("txt", "")} 
                            for o in opt_q.get('opts', [])
                        ]
                        
        return merged

    
    def _parse_json(self, result_text: str) -> Dict:
        """解析 JSON 响应"""
        try:
            # 如果返回的是 markdown 格式的 json，需要提取
            if "```json" in result_text:
                json_start = result_text.find("```json") + 7
                json_end = result_text.find("```", json_start)
                result_text = result_text[json_start:json_end].strip()
            if "```" in result_text:
                json_start = result_text.find("```") + 3
                json_end = result_text.find("```", json_start)
                if json_end != -1:
                    result_text = result_text[json_start:json_end].strip()
                else:
                    result_text = result_text[json_start:].strip()
            
            # 使用 json_repair 处理常见的大模型 JSON 语法截断或格式错误
            parsed = json_repair.loads(result_text)
            if not isinstance(parsed, dict):
                # 如果依然没解析出有效的字典，尝试封装一下
                return {"text_result": str(parsed)}
            return parsed
        
        except Exception as e:
            print(f"❌ JSON 解析失败/修复失败: {e}")
            print(f"原始返回（前500字符）: {result_text[:500]}")
            
            # 返回错误信息
            return {
                "error": "JSON解析及自动修复失败",
                "error_detail": str(e),
                "raw_response": result_text[:1000]
            }
