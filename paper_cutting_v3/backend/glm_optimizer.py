#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLM 优化器 V3 - 三段式管线
  Stage 1: 阿里云 OCR（坐标分区，粗糙文字）
  Stage 2: GLM-OCR layout_parsing（精准识别：公式/圆圈/表格）
  Stage 3: GLM-4 对话模型（按 Pydantic 结构化整理）
"""
import json
import base64
import io
import os
import concurrent.futures
from typing import Dict, List, Optional

from PIL import Image
from pydantic import BaseModel, Field

try:
    from openai import OpenAI
except ImportError:
    print("⚠️ 需要安装 openai: pip install openai")
    OpenAI = type('OpenAI', (), {})

try:
    from zai import ZhipuAiClient
except ImportError:
    print("⚠️ 需要安装 zai-sdk: pip install zai-sdk")
    ZhipuAiClient = type('ZhipuAiClient', (), {})

import json_repair


# ==========================================
# Pydantic 结构定义
# ==========================================

class Option(BaseModel):
    id: str = Field(description="选项标识，如 'A'、'①'、'C' 等")
    txt: str = Field(description="选项具体内容")

class SubQuestion(BaseModel):
    no: str = Field(description="小问编号，如 '1'、'2' 等")
    content: str = Field(description="该子题内容")

class OptimizedQuestion(BaseModel):
    id: str = Field(description="必须严格保留传入的原题 ID，不可修改！")
    prompt: Optional[str] = Field(default=None, description="题干引导语，如'填空题'、'选择题'")
    content: str = Field(description="题目实质正文（不含选项）。数学公式用 $...$ 包裹。")
    opts: Optional[List[Option]] = Field(default_factory=list, description="选项数组")
    subqs: Optional[List[SubQuestion]] = Field(default_factory=list, description="子题数组")


# ==========================================
# GLM 优化器
# ==========================================

class GLMOptimizer:
    """三段式管线优化器：GLM-OCR 精准识别 → GLM-4 结构化整理"""

    def __init__(self, api_key: str):
        if not OpenAI:
            raise ImportError("请先安装 openai: pip install openai")
        if not ZhipuAiClient:
            raise ImportError("请先安装 zai-sdk: pip install zai-sdk")

        # Stage 2: GLM-OCR 专用客户端（layout_parsing 接口）
        self.ocr_client = ZhipuAiClient(api_key=api_key)

        # Stage 3: 对话模型客户端（结构化整理）
        self.chat_client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )
        self.struct_model = "glm-4-flash"  # 结构化整理用 flash 足够，省钱

    # ------------------------------------------
    # 公开接口：批量优化全部题目
    # ------------------------------------------

    def optimize(self, aliyun_result: Dict, image_url: Optional[str] = None) -> Dict:
        """批量优化所有题目"""
        import copy
        merged = copy.deepcopy(aliyun_result)

        source_image = None
        if image_url and os.path.exists(image_url):
            try:
                source_image = Image.open(image_url)
            except Exception as e:
                print(f"⚠️ 图片读取失败，降级为纯文本模式: {e}")

        tasks = []
        for p_idx, part in enumerate(merged.get('parts', [])):
            for q_idx, q in enumerate(part.get('questions', [])):
                img_b64 = self._crop_question_image(source_image, q)
                tasks.append((p_idx, q_idx, q, img_b64))

        def process_task(args):
            p_idx, q_idx, q, b64 = args
            try:
                result = self.optimize_single(q, image_b64=b64)
                return p_idx, q_idx, result
            except Exception as e:
                print(f"题目 {q.get('id')} 优化异常: {e}")
                return p_idx, q_idx, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(process_task, tasks))

        for p_idx, q_idx, opt_q in results:
            if opt_q:
                q = merged['parts'][p_idx]['questions'][q_idx]
                self._merge_optimized(q, opt_q)

        return merged

    # ------------------------------------------
    # 公开接口：单题优化（三段式）
    # ------------------------------------------

    def optimize_single(self, question_data: Dict, image_b64: Optional[str] = None) -> Dict:
        """
        三段式管线：
          Stage 2: GLM-OCR → 精准 OCR 文字
          Stage 3: GLM-4   → 结构化 JSON
        """
        # --- Stage 2: GLM-OCR 精准识别 ---
        ocr_text = None
        if image_b64:
            ocr_text = self._glm_ocr(image_b64)

        # --- Stage 3: GLM-4 结构化整理 ---
        return self._structure(question_data, ocr_text)

    # ------------------------------------------
    # Stage 2: GLM-OCR 精准识别
    # ------------------------------------------

    def _glm_ocr(self, image_b64: str) -> Optional[str]:
        """调用 GLM-OCR layout_parsing 接口，返回清洗后的 Markdown 文字"""
        import re
        try:
            response = self.ocr_client.layout_parsing.create(
                model="glm-ocr",
                file=f"data:image/jpeg;base64,{image_b64}"
            )
            text = response.md_results
            if not text:
                return None
            # 将 layout_parsing 返回的图片占位符 ![](...) 普遍替换为 $\bigcirc$
            # 这些图片占位符通常在小学数学题目中代表需填写的圆圈
            text = re.sub(r'!\[\]\([^)]+\)', '$\\bigcirc$', text)
            return text
        except Exception as e:
            print(f"⚠️ GLM-OCR 识别失败，降级为阿里云文字: {e}")
            return None

    # ------------------------------------------
    # Stage 3: GLM-4 结构化
    # ------------------------------------------

    def _structure(self, question_data: Dict, ocr_text: Optional[str]) -> Dict:
        """用 GLM-4 将 OCR 文字整理为 OptimizedQuestion 结构"""
        q_id = question_data.get('id', '')
        aly_text = self._format_aliyun_text(question_data)

        # 构建输入：优先用 GLM-OCR 文字，同时提供阿里云结果作参考
        if ocr_text:
            user_input = f"""【系统分配题号】: {q_id} （请原封不动填入 id 字段）
【基本题型参考】: {question_data.get('type_name', question_data.get('type', '未知'))}

=== 阿里云粗糙文字（作为线索，帮你在下方长文本中定位本题原本的样子和前缀题号）===
{aly_text}

=== GLM-OCR 高精度识别文字（以此为最终提取准则，包含完整数学公式和排版）===
{ocr_text}"""
        else:
            user_input = f"""【系统分配题号】: {q_id} （请原封不动填入 id 字段）
【基本题型参考】: {question_data.get('type_name', question_data.get('type', '未知'))}

=== 阿里云识别文字 ===
{aly_text}"""

        system_prompt = """你是一个试卷题目结构化大模型。
请在传入的文字中提取出指定的唯一一道题目。
因为传入的“GLM-OCR高精度文字”可能包含了图片上下截取到的其他多道干扰题目，**你必须对照那段“阿里云粗糙文字”作为线索，找到这道题的真正边界（开头和结尾）**，把它的对应内容完整提取出来！

必须严格整理为以下 JSON 格式输出，不要输出其他任何思维过程或讲解：

```json
{
  "id": "（填入用户传入的 系统分配题号，必须一字不改）",
  "prompt": "（在这道题抽出的提问引导语，如'填空题'、'选择题'，若无则 null）",
  "content": "（提取出的这道题的正文，不含选项！不能有其他干扰题干！数学公式等保持 $...$ 格式）",
  "opts": [{"id": "选项标识", "txt": "选项内容"}],
  "subqs": []
}
```

规则：
1. **只提取匹配“阿里云文字”特征的那一道题！绝不可以把上下相邻的题干也吞并进来！**
2. 填空题的空白（    ）、算式中的 $\\bigcirc$ 占位圆圈等必须完整保留在 content 里。绝对不能把代表留空的括号当成选择题的选项提取！
3. 若本题有真正的单选或多选选项（如 A. B. C. 或者 ① ② ③ 配合选项文字），必须提取到 opts 数组里；否则 opts 返回空数组 []。
4. 不要做任何解题、补全或补充额外知识，忠于原始考卷的文本和排版即可。"""

        try:
            response = self.chat_client.chat.completions.create(
                model=self.struct_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1
            )
            result_text = response.choices[0].message.content

            # 提取 JSON 块
            if "```json" in result_text:
                start = result_text.find("```json") + 7
                end = result_text.find("```", start)
                if end != -1:
                    result_text = result_text[start:end].strip()
            elif "```" in result_text:
                start = result_text.find("```") + 3
                end = result_text.find("```", start)
                if end != -1:
                    result_text = result_text[start:end].strip()

            result_dict = json_repair.loads(result_text)
            if not isinstance(result_dict, dict):
                raise ValueError(f"返回格式并非字典: {result_text}")

            validated = OptimizedQuestion.model_validate(result_dict)
            return validated.model_dump(exclude_none=True)

        except Exception as e:
            print(f"❌ 结构化整理失败 [{q_id}]: {e}")
            raise

    # ------------------------------------------
    # 工具方法
    # ------------------------------------------

    def _crop_question_image(self, source_image: Optional[Image.Image], q: Dict) -> Optional[str]:
        """按 position 裁切题目图片，返回 base64 字符串
        裁切略大，确保多行算式和题目译文都在范围内
        """
        if not source_image or not q.get('position'):
            return None
        try:
            pos = q['position']
            # 为了防止左右内容被阿里云残缺的 bbox 截断，横向（X轴）尽量拉满，只保留少量边距
            # 或者给极大的 pad_x
            pad_x = max(100, pos['width'] // 2) 
            pad_top = 30
            pad_bottom = max(100, pos['height'] * 2)  # 底部大幅扩展，防止多行内容被截
            box = (
                max(0, pos['x'] - pad_x),
                max(0, pos['y'] - pad_top),
                min(source_image.width, pos['x'] + pos['width'] + pad_x),
                min(source_image.height, pos['y'] + pos['height'] + pad_bottom)
            )
            cropped = source_image.crop(box)
            buf = io.BytesIO()
            if cropped.mode != 'RGB':
                cropped = cropped.convert('RGB')
            cropped.save(buf, format="JPEG")
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"⚠️ 题目 {q.get('id')} 裁切失败: {e}")
            return None

    def _format_aliyun_text(self, q: Dict) -> str:
        """格式化阿里云识别的粗糙文本"""
        lines = [q.get('text', '')]
        if q.get('options'):
            for opt in q['options']:
                lines.append(f"  {opt.get('option', '')} {opt.get('text', '')}")
        return "\n".join(lines)

    def _merge_optimized(self, q: Dict, opt_q: Dict):
        """将优化结果合并回原题目数据"""
        q['glm_optimized'] = opt_q
        if opt_q.get('prompt'):
            q['type_name'] = opt_q['prompt']
        q['text'] = opt_q.get('content') or q.get('text', '')
        if opt_q.get('opts'):
            q['options'] = [
                {"option": o.get("id", ""), "text": o.get("txt", "")}
                for o in opt_q.get('opts', [])
            ]
