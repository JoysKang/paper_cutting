"""
试卷试题切割整理工具
功能：
1. 使用 glm-ocr 识别试卷图片，获取 Markdown 内容
2. 保存 OCR 结果到文件，方便调试
3. 使用 glm-4.6v 将图片和 MD 内容整理成结构化 JSON
"""

from zai import ZhipuAiClient
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import time
from urllib.parse import unquote, urlparse

# ==================== 配置常量 ====================

# API配置
API_KEY = "74437791901b4ebe88c2b95d5041d92c.3LgLCf8DudPNJxxr"
# 小学数学
# FILE_PATH = "https://ynx-test.oss-cn-beijing.aliyuncs.com/paper/%E6%95%B0%E5%AD%A6/full.jpg"
FILE_PATH = "https://ynx-test.oss-cn-beijing.aliyuncs.com/paper/%E6%95%B0%E5%AD%A6/%E4%B8%89%E5%B9%B4%E7%BA%A7%E4%B8%8A%E5%AD%A6%E6%9C%9F%E6%95%B0%E5%AD%A6%E5%8D%B7.pdf"

# 小学语文
# FILE_PATH = "https://ynx-test.oss-cn-beijing.aliyuncs.com/paper/%E8%AF%AD%E6%96%87/%E4%B8%89%E5%B9%B4%E7%BA%A7%E6%9C%9F%E6%9C%AB%E8%AF%95%E5%8D%B7%E8%AF%AD%E6%96%87%281%29.pdf"

# 试卷信息（用于选择提示词）
GRADE_LEVEL = "primary"  # primary(小学) / junior(初中) / senior(高中)
# SUBJECT = "chinese"      # chinese(语文) / math(数学) / english(英语) 等
SUBJECT = "math"      # chinese(语文) / math(数学) / english(英语) 等

# 模型配置
OCR_MODEL = "glm-ocr"
VISION_MODEL = "glm-4.6v-flash"
VISION_TEMPERATURE = 0.1

# 目录配置
OUTPUT_DIR = Path("output")
# 使用脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent
PROMPTS_DIR = SCRIPT_DIR / "prompts"


# ==================== 核心类 ====================


class ExamProcessor:
    """试卷处理器"""
    
    def __init__(self, api_key: str, output_dir: Path = OUTPUT_DIR, prompts_dir: Path = PROMPTS_DIR):
        """
        初始化客户端
        
        Args:
            api_key: API密钥
            output_dir: 输出目录，默认为 OUTPUT_DIR
            prompts_dir: 提示词目录，默认为 PROMPTS_DIR
        """
        self.client = ZhipuAiClient(api_key=api_key)
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir = prompts_dir
    
    def _extract_filename_from_url(self, url: str) -> str:
        """
        从URL中提取文件名（不含扩展名）
        
        Args:
            url: 文件URL
            
        Returns:
            文件名（不含扩展名）
        """
        # 解析URL
        parsed = urlparse(url)
        # 获取路径部分
        path = parsed.path
        # 提取文件名
        filename = Path(path).name
        # URL解码（处理中文等特殊字符）
        filename = unquote(filename)
        # 去掉扩展名
        filename_without_ext = Path(filename).stem
        return filename_without_ext
    
    def load_prompts(self, grade_level: str, subject: str) -> str:
        """
        加载提示词（基础 + 学科）
        
        Args:
            grade_level: 学段（primary/junior/senior）
            subject: 科目（chinese/math/english等）
            
        Returns:
            组合后的完整提示词
        """
        prompts = []
        
        # 1. 加载基础提示词
        base_prompt_file = self.prompts_dir / "exam-paper-base" / "base.md"
        if base_prompt_file.exists():
            with open(base_prompt_file, 'r', encoding='utf-8') as f:
                prompts.append(f.read())
            print(f"[提示词] 已加载基础提示词: {base_prompt_file}")
        else:
            print(f"[警告] 基础提示词文件不存在: {base_prompt_file}")
        
        # 2. 加载学科提示词
        subject_prompt_file = self.prompts_dir / grade_level / subject / "prompt.md"
        if subject_prompt_file.exists():
            with open(subject_prompt_file, 'r', encoding='utf-8') as f:
                prompts.append(f.read())
            print(f"[提示词] 已加载学科提示词: {subject_prompt_file}")
        else:
            print(f"[警告] 学科提示词文件不存在: {subject_prompt_file}")
        
        # 3. 组合提示词
        combined_prompt = "\n\n**以上为最近本要求**\n\n".join(prompts)
        print(f"[提示词] 提示词总长度: {len(combined_prompt)} 字符")
        
        return combined_prompt
    
    def ocr_recognize(self, file_url: str) -> dict:
        """
        步骤1: 使用 glm-ocr 识别文件（支持图片和PDF的URL）
        
        Args:
            file_url: 文件 URL（格式：PDF、JPG、PNG）
            
        Returns:
            OCR识别结果（dict格式）
        """
        print(f"[OCR识别] 开始识别文件: {file_url}")
        start_time = time.time()
        
        try:
            response = self.client.layout_parsing.create(
                model=OCR_MODEL,
                file=file_url,
                return_crop_images=True  # 返回裁剪图片信息
            )
            
            elapsed = time.time() - start_time
            print(f"[OCR识别] 识别完成，耗时: {elapsed:.2f}秒")
            
        except Exception as e:
            print(f"[OCR识别] 调用失败: {e}")
            print(f"[OCR识别] 错误类型: {type(e).__name__}")
            raise
        
        # 将 LayoutParsingResp 对象转换为 dict
        if hasattr(response, 'model_dump'):
            return response.model_dump()
        elif hasattr(response, 'dict'):
            return response.dict()
        else:
            # 降级处理：手动转换
            return {
                'id': response.id,
                'created': response.created,
                'model': response.model,
                'md_results': response.md_results,
                'layout_details': response.layout_details,
                'layout_visualization': response.layout_visualization,
                'data_info': response.data_info,
                'usage': response.usage,
                'request_id': response.request_id,
            }
    
    def save_ocr_result(self, ocr_result: dict, filename: Optional[str] = None) -> str:
        """
        步骤2: 保存 OCR 结果到文件
        
        Args:
            ocr_result: OCR识别结果
            filename: 文件名（可选）
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ocr_result_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(ocr_result, f, ensure_ascii=False, indent=2)
        
        print(f"[保存结果] OCR结果已保存到: {filepath}")
        return str(filepath)
    
    def extract_markdown(self, ocr_result: dict) -> tuple[str, list[dict]]:
        """
        从 OCR 结果中提取 Markdown 内容和图片信息
        
        Args:
            ocr_result: OCR识别结果
            
        Returns:
            (Markdown格式的文本内容, 图片信息列表)
        """
        # 提取图片位置信息和URL
        image_info = []
        layout_details = ocr_result.get('layout_details', [])
        
        for page_idx, page in enumerate(layout_details):
            for item in page:
                if item.get('label') == 'image':
                    image_info.append({
                        'index': item.get('index'),
                        'bbox': item.get('bbox_2d'),
                        'page': page_idx,
                        'url': item.get('content')
                    })
        
        # 使用 OCR 返回的 md_results 字段
        markdown_content = ocr_result.get('md_results', '')
        
        return markdown_content, image_info
    
    def save_markdown(self, markdown_content: str, image_info: list[dict], filename: Optional[str] = None) -> str:
        """
        保存 Markdown 内容到文件
        
        Args:
            markdown_content: Markdown内容
            image_info: 图片信息列表（用于统计）
            filename: 文件名（可选）
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ocr_markdown_{timestamp}.md"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"[保存结果] Markdown内容已保存到: {filepath}")
        print(f"[图片信息] 识别到 {len(image_info)} 张图片")
        return str(filepath)
    
    def structure_with_glm(self, file_path: str, markdown_file: str, image_info: list[dict], grade_level: str, subject: str) -> dict:
            """
            步骤3: 使用 glm-4.6v 将文件和 MD 内容整理成结构化 JSON

            Args:
                file_path: 原始文件 URL
                markdown_file: Markdown文件路径
                image_info: 图片位置信息列表
                grade_level: 学段（primary/junior/senior）
                subject: 科目（chinese/math/english等）

            Returns:
                结构化的试卷JSON数据
            """
            print(f"[结构化处理] 开始使用 {VISION_MODEL} 处理...")
            print(f"[结构化处理] 学段: {grade_level}, 科目: {subject}")
            start_time = time.time()

            # 读取 Markdown 文件内容
            with open(markdown_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()

            # 使用 file_url 类型传递文件 URL
            vision_content = {
                "type": "file_url",
                "file_url": {"url": file_path}
            }

            # 加载提示词
            prompt_template = self.load_prompts(grade_level, subject)

            # 构建图片信息说明
            image_desc = ""
            if image_info:
                image_desc = f"识别到 {len(image_info)} 张图片。"

            # 构建完整提示词
            prompt = f"""{prompt_template}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    现在开始处理以下OCR识别内容
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    {image_desc}

    OCR识别内容：
    {markdown_content}
    """

            # 调用 glm-4.6v
            response = self.client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            vision_content,
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                temperature=VISION_TEMPERATURE,
                response_format={"type": "json_object"}
            )

            elapsed = time.time() - start_time

            # 提取并解析JSON结果
            result_text = response.choices[0].message.content
            structured_data = self._parse_json_response(result_text)

            print(f"[结构化处理] 处理完成，耗时: {elapsed:.2f}秒")
            return structured_data
    
    def _parse_json_response(self, result_text: str) -> dict:
        """
        解析模型返回的JSON响应
        
        Args:
            result_text: 模型返回的文本
            
        Returns:
            解析后的JSON数据
        """
        try:
            # 如果返回的是markdown格式的json，需要提取
            if "```json" in result_text:
                json_start = result_text.find("```json") + 7
                json_end = result_text.find("```", json_start)
                result_text = result_text[json_start:json_end].strip()
            elif "```" in result_text:
                json_start = result_text.find("```") + 3
                json_end = result_text.find("```", json_start)
                result_text = result_text[json_start:json_end].strip()
            
            return json.loads(result_text)
        except json.JSONDecodeError as e:
            print(f"[错误] JSON解析失败: {e}")
            print(f"[原始返回] {result_text[:500]}...")
            return {
                "error": "JSON解析失败",
                "error_detail": str(e)
            }
    
    def save_structured_result(self, structured_data: dict, filename: Optional[str] = None) -> str:
        """
        保存结构化结果
        
        Args:
            structured_data: 结构化数据
            filename: 文件名（可选）
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"exam_structured_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)
        
        print(f"[保存结果] 结构化数据已保存到: {filepath}")
        return str(filepath)
    
    def process_exam(self, file_url: str, grade_level: str = "primary", subject: str = "chinese") -> dict:
        """
        完整处理流程：OCR识别 -> 保存中间结果 -> 结构化处理
        
        Args:
            file_url: 试卷文件 URL（格式：PDF、JPG、PNG）
            grade_level: 学段（primary/junior/senior），默认为 primary
            subject: 科目（chinese/math/english等），默认为 chinese
            
        Returns:
            处理结果，包含所有文件路径和结构化数据
        """
        print("=" * 60)
        print("开始处理试卷")
        print(f"学段: {grade_level}, 科目: {subject}")
        print("=" * 60)
        
        total_start_time = time.time()
        
        # 从URL中提取文件名（不含扩展名）
        base_filename = self._extract_filename_from_url(file_url)
        print(f"[文件名] {base_filename}")
        
        # 步骤1: OCR识别
        ocr_result = self.ocr_recognize(file_url)
        ocr_file = self.save_ocr_result(ocr_result, filename=f"{base_filename}_ocr.json")
        
        # 步骤2: 提取并保存Markdown和图片信息
        markdown_content, image_info = self.extract_markdown(ocr_result)
        md_file = self.save_markdown(markdown_content, image_info, filename=f"{base_filename}_ocr.md")
        
        # 步骤3: 结构化处理（传递学段和科目信息）
        structured_data = self.structure_with_glm(file_url, md_file, image_info, grade_level, subject)
        json_file = self.save_structured_result(structured_data, filename=f"{base_filename}.json")
        
        total_elapsed = time.time() - total_start_time
        
        print("=" * 60)
        print(f"处理完成！总耗时: {total_elapsed:.2f}秒")
        print("=" * 60)
        
        return {
            "filename": base_filename,
            "total_time": f"{total_elapsed:.2f}s",
            "ocr_file": ocr_file,
            "markdown_file": md_file,
            "structured_file": json_file,
            "structured_data": structured_data,
            "image_count": len(image_info)
        }


# ==================== 主函数 ====================


def main():
    """主函数"""
    # 创建处理器
    processor = ExamProcessor(api_key=API_KEY)
    
    # 处理试卷（使用配置的学段和科目）
    result = processor.process_exam(FILE_PATH, grade_level=GRADE_LEVEL, subject=SUBJECT)
    
    # 输出结果
    print("\n处理结果：")
    print(f"  文件名: {result['filename']}")
    print(f"  总耗时: {result['total_time']}")
    print(f"  OCR结果文件: {result['ocr_file']}")
    print(f"  Markdown文件: {result['markdown_file']}")
    print(f"  结构化JSON文件: {result['structured_file']}")
    print(f"  识别图片数: {result['image_count']}")


if __name__ == "__main__":
    main()
