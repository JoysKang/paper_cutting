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
    id: str = Field(description="必须严格保留或分配子ID（如 1-7-1）！")
    prompt: Optional[str] = Field(default=None, description="题干引导语，如'填空题'、'选择题'")
    content: str = Field(description="题目实质正文（不含选项）。数学公式用 $...$ 包裹。")
    opts: Optional[List[Option]] = Field(default_factory=list, description="选项数组")
    subqs: Optional[List[SubQuestion]] = Field(default_factory=list, description="子题数组")

class OptimizedResult(BaseModel):
    questions: List[OptimizedQuestion]


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
传入的“阿里云粗糙文字”提供了你**真正需要提取的内容范围的线索**。
由于前置 OCR 的切分问题：
1. 一方面，多道题目可能在“阿里云粗糙文字”中粘连在一起（比如包含第7和第8题）。你必须将它们**拆开**，放到 `questions` 数组中独立输出。
2. 另一方面，长文本片段“GLM-OCR高精度文字”中可能会多出很多**完全没有在“阿里云粗糙文字”里出现过**的周边干扰题目/图文（比如下一题、或者旁边的无关段落）。你必须将这些干扰内容**毫不留情地全部丢弃**，绝对不能也把它们提取成题目！

必须严格整理为以下 JSON 格式输出，不要输出其他任何思维过程或讲解：

```json
{
  "questions": [
    {
      "id": "（若是单题，填入原题号即可；如果是拆分出的多道题目，可加后缀如 '1-7_1', '1-7_2' 等以示区分）",
      "prompt": "（在这段文字开头抽出的提问引导语，如'填空题'、'选择题'，若无则 null）",
      "content": "（提取出的正文。如果是拆分后的独立题目，必须包含属于这道题开头的连串题号如'7.', '8.'等，数学公式保持 $...$ 格式）",
      "opts": [{"id": "选项标识", "txt": "选项内容"}],
      "subqs": []
    }
  ]
}
```

规则：
规则：
1. **【剔除多余干扰题，这是死命令！】只要某段文字（或某道题）在“阿里云粗糙文字”中找不到明显的对应线索，它就是由于截图范围过大卷进来的多余垃圾！绝不可以将其算作一道题输出到 JSON 里！一定要丢弃它！**
2. **【核心正文必须以 GLM-OCR 为准】阿里云只有粗糙文字并容易丢失公式/符号（如 $\\bigcirc$ 等）。所以你的提取内容必须完全采用“GLM-OCR高精度文字”中的文字、排版和 LaTeX 公式表达式，不能盲目照抄阿里云！**
3. **【拆分连体题】** 如果“阿里云粗糙文字”包含不止一道题，你要在保证不多提取无关题目的前提下，把它们正确地拆分成数组里独立的 `{}` 对象。
4. **【极其重点！！！保留原题号】提取出的每道题的 `content` 第一个字必须完全还原该题的题号（例如 `7.`、`8.`）。哪怕 GLM-OCR 的长文本中弄丢了它，你也必须手动将 `7.` 之类的文本补在 `content` 最前方。绝对不能吞掉题号！**
5. 填空题的留空（    ）、大小圆圈（$\\bigcirc$ 等占位符）必须【完全按照 GLM-OCR 中的样子】原样保留在 content 里。绝对不能把代表留空的括号当成选择题的选项提取！
6. 选项、小题依然像以前一样分别放入 `opts` / `subqs` 取代。图片配图等无意义代码标识如 `![](page...)` 可以直接忽略。"""

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
            if result_text is None:
                result_text = ""
                
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

            import re
            # 修复：防止大模型在 JSON 里把 LaTeX 单斜杠（如 \bigcirc, \triangle）输出导致
            # 被 Python JSON 解析器当作 \b (backspace) 或 \t (tab) 转义，统一强制转为双斜杠
            if isinstance(result_text, str):
                result_text = re.sub(
                    r'(?<!\\)\\(bigcirc|triangle|div|times|textcircled|Box|left|right|cdot|leqslant|geqslant)', 
                    r'\\\\\1', 
                    result_text
                )

            result_dict = json_repair.loads(result_text)
            if not isinstance(result_dict, dict):
                raise ValueError(f"返回格式并非字典: {result_text}")

            # 兼容：如果它返回的是老格式单个题目，包成 list
            if 'questions' not in result_dict:
                if 'id' in result_dict and 'content' in result_dict:
                    result_dict = {"questions": [result_dict]}
                else:
                    raise ValueError(f"返回格式缺少 questions 数组: {result_text}")

            for q_dict in result_dict['questions']:
                # 强力洗掉所有依然残留进来的 ![](page=0,...) 图片占位符
                if q_dict.get('content'):
                    content_text = re.sub(r'!\[.*?\]\(page=[^)]+\)', '', q_dict['content']).strip()
                    # 如果只有一道题，做下双保险兜底
                    if len(result_dict['questions']) == 1:
                        prefix_match = re.match(r'^([0-9]+\.|[①-⑨])', aly_text.strip())
                        if prefix_match:
                            prefix = prefix_match.group(1)
                            if not content_text.startswith(prefix):
                                content_text = f"{prefix}{content_text}"
                    q_dict['content'] = content_text

            validated = OptimizedResult.model_validate(result_dict)
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
