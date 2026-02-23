#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云精细版结构化切题脚本
用于识别试卷图片中的试题,包括题目内容、选项、作答区域和图片
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from alibabacloud_ocr_api20210707.client import Client as OcrClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_ocr_api20210707 import models as ocr_models  # ty:ignore[unresolved-import]
from alibabacloud_tea_util import models as util_models
import io


class AliyunPaperOCR:
    """阿里云试卷OCR识别类"""

    def __init__(self, access_key_id: str, access_key_secret: str):
        """
        初始化客户端

        Args:
            access_key_id: 阿里云AccessKey ID
            access_key_secret: 阿里云AccessKey Secret
        """
        config = open_api_models.Config(
            access_key_id=access_key_id, access_key_secret=access_key_secret
        )
        config.endpoint = "ocr-api.cn-hangzhou.aliyuncs.com"
        self.client = OcrClient(config)

    def recognize_paper(
        self,
        image_path: str = None,
        image_url: str = None,
        subject: str = "default",
        need_rotate: bool = True,
        output_origin_points: bool = True,
        extract_images: bool = False,
        output_dir: str = None,
        min_figure_area: int = 2000,
        extract_figures: bool = True,
        extract_answer_areas: bool = False,
    ) -> Dict:
        """
        识别试卷图片

        Args:
            image_path: 本地图片路径
            image_url: 图片URL地址
            subject: 年级学科(default, Math, Chinese, English等)
            need_rotate: 是否需要自动旋转
            output_origin_points: 是否输出原图坐标
            extract_images: 是否提取题目中的图片
            output_dir: 图片输出目录
            min_figure_area: 图片最小面积阈值
            extract_figures: 是否切图提取题目配图
            extract_answer_areas: 是否切图提取作答区域

        Returns:
            识别结果字典
        """
        start_time = time.time()

        request = ocr_models.RecognizeEduPaperStructedRequest()

        # 设置图片来源(URL或本地文件二选一)
        if image_url:
            request.url = image_url
        elif image_path:
            with open(image_path, "rb") as f:
                request.body = io.BytesIO(f.read())
        else:
            raise ValueError("必须提供 image_path 或 image_url 之一")

        # 设置识别参数
        request.type = subject
        request.need_rotate = need_rotate
        request.output_origin_points = output_origin_points

        runtime = util_models.RuntimeOptions()

        try:
            response = self.client.recognize_edu_paper_structed_with_options(
                request, runtime
            )
            result = response.body.to_map()

            elapsed_time = time.time() - start_time
            print(f"⏱️  OCR识别耗时: {elapsed_time:.2f}秒")

            # 如果需要提取图片
            if extract_images and image_path and output_dir:
                questions = self.parse_questions(result, page_index=1)
                self._extract_question_images(
                    questions,
                    image_path,
                    output_dir,
                    min_figure_area=min_figure_area,
                    extract_figures=extract_figures,
                    extract_answer_areas=extract_answer_areas,
                )

            return result
        except Exception as e:
            print(f"识别失败: {str(e)}")
            raise

    def recognize_exam_directory(
        self,
        exam_dir: str,
        subject: str = "default",
        need_rotate: bool = True,
        output_origin_points: bool = True,
        extract_images: bool = True,
        output_dir: str = "extracted_images",
        save_raw_ocr: Optional[str] = None,  # 保存原始OCR结果的文件路径
        save_processed: Optional[str] = None,  # 保存处理后结果的文件路径
        min_figure_area: int = 2000,
        extract_figures: bool = True,
        extract_answer_areas: bool = False,
    ) -> Dict:
        """
        识别整个试卷目录

        Args:
            exam_dir: 试卷图片目录
            subject: 年级学科
            need_rotate: 是否需要自动旋转
            output_origin_points: 是否输出原图坐标
            extract_images: 是否提取题目中的图片
            output_dir: 图片输出目录
            save_raw_ocr: 保存原始OCR结果的JSON文件路径(如aly.json)
            save_processed: 保存处理后结果的JSON文件路径(如out.json)
            min_figure_area: 图片最小面积阈值
            extract_figures: 是否切图提取题目配图
            extract_answer_areas: 是否切图提取作答区域

        Returns:
            优化后的结构化数据
        """
        total_start_time = time.time()

        image_files = self._list_image_files(exam_dir)
        if not image_files:
            raise ValueError(f"目录中未找到图片文件: {exam_dir}")

        print(f"📁 找到 {len(image_files)} 张图片")
        
        # 使用parts结构来组织所有题目
        all_parts = []
        total_questions_count = 0
        extracted_images_count = 0
        all_raw_ocr_results = []  # 保存所有原始OCR结果

        for page_index, image_path in enumerate(image_files, 1):
            print(
                f"\n📄 [{page_index}/{len(image_files)}] 正在识别: {os.path.basename(image_path)}"
            )
            page_start_time = time.time()

            ocr_result = self.recognize_paper(
                image_path=image_path,
                subject=subject,
                need_rotate=need_rotate,
                output_origin_points=output_origin_points,
            )
            
            # 保存原始OCR结果
            # 注意: ocr_result中的Data字段可能是JSON字符串,需要反序列化
            ocr_result_to_save = ocr_result.copy()
            if isinstance(ocr_result_to_save.get("Data"), str):
                try:
                    ocr_result_to_save["Data"] = json.loads(ocr_result_to_save["Data"])
                except (json.JSONDecodeError, TypeError):
                    pass  # 如果解析失败,保持原样
            
            all_raw_ocr_results.append({
                "page": page_index,
                "image": os.path.basename(image_path),
                "ocr_result": ocr_result_to_save
            })
            
            parsed_result = self.parse_questions(ocr_result, page_index=page_index)

            # 提取图片
            if extract_images:
                page_output_dir = os.path.join(output_dir, f"page_{page_index}")
                extracted_count = self._extract_question_images(
                    parsed_result,
                    image_path,
                    page_output_dir,
                    min_figure_area=min_figure_area,
                    extract_figures=extract_figures,
                    extract_answer_areas=extract_answer_areas,
                )
                extracted_images_count += extracted_count
                if extracted_count > 0:
                    print(f"   🖼️  提取了 {extracted_count} 张图片")

            # 为每个部分的题目添加页面信息
            page_question_count = 0
            for part in parsed_result.get("parts", []):
                for question in part.get("questions", []):
                    question["page"] = page_index
                    question["source_image"] = os.path.basename(image_path)
                    page_question_count += 1
                    total_questions_count += 1

            page_elapsed = time.time() - page_start_time
            print(f"   ✓ 识别到 {page_question_count} 道题目 (耗时: {page_elapsed:.2f}秒)")

            # 合并parts(如果跨页有相同的part_title,则合并)
            for part in parsed_result.get("parts", []):
                existing_part = next(
                    (p for p in all_parts if p["title"] == part["title"]), None
                )
                if existing_part:
                    existing_part["questions"].extend(part["questions"])
                else:
                    all_parts.append(part)

        total_elapsed = time.time() - total_start_time
        
        print(f"\n{'=' * 60}")
        print(f"✅ 识别完成!")
        print(f"   总题目数: {total_questions_count}")
        print(f"   提取图片数: {extracted_images_count}")
        print(f"   总耗时: {total_elapsed:.2f}秒")
        print(f"   平均每页: {total_elapsed / len(image_files):.2f}秒")
        print(f"{'=' * 60}")

        # 构建处理后的结果
        processed_result = {
            "metadata": {
                "exam_dir": os.path.abspath(exam_dir),
                "total_pages": len(image_files),
                "total_questions": total_questions_count,
                "extracted_images": extracted_images_count,
                "total_elapsed_time": round(total_elapsed, 2),
                "image_output_dir": os.path.abspath(output_dir) if extract_images else None,
            },
            "parts": all_parts,
        }
        
        # 保存原始OCR结果到文件
        if save_raw_ocr:
            with open(save_raw_ocr, 'w', encoding='utf-8') as f:
                json.dump(all_raw_ocr_results, f, ensure_ascii=False, indent=2)
            print(f"\n💾 原始OCR结果已保存到: {save_raw_ocr}")
        
        # 保存处理后的结果到文件
        if save_processed:
            with open(save_processed, 'w', encoding='utf-8') as f:
                json.dump(processed_result, f, ensure_ascii=False, indent=2)
            print(f"💾 处理后结果已保存到: {save_processed}")

        return processed_result

    def parse_questions(self, ocr_result: Dict, page_index: Optional[int] = None) -> Dict:
        """
        解析识别结果,提取题目信息

        Args:
            ocr_result: OCR识别结果

        Returns:
            按部分组织的题目结构
        """
        parts = []

        # 获取data字段
        data = ocr_result.get("Data") or ocr_result.get("data")
        if not data:
            return {"parts": parts}

        # 如果data是字符串,尝试解析
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                return {"parts": parts}

        # 获取顶层的 figure 数组(包含所有图片信息)
        all_figures = data.get("figure", [])

        # 获取part_info
        part_info = data.get("part_info", [])

        # 遍历题型大类
        for part_index, part in enumerate(part_info, 1):
            part_title = part.get("part_title", "")
            questions = []

            # 遍历该题型下的所有题目
            for q_index, subject in enumerate(part.get("subject_list", []), 1):
                question = self._parse_subject(
                    subject, part_index, q_index, part_title, all_figures, page_index
                )
                if question:
                    questions.append(question)

            if questions:
                parts.append(
                    {"title": part_title, "questions": questions}
                )

        return {"parts": parts}

    def _parse_subject(
        self,
        subject: Dict,
        part_index: int,
        q_index: int,
        part_title: str,
        all_figures: List[Dict],
        page_index: Optional[int],
    ) -> Optional[Dict]:
        """
        解析单个题目

        Args:
            subject: 题目数据
            part_index: 部分索引
            q_index: 题目在部分中的索引
            part_title: 题型名称
            all_figures: 顶层的所有图片信息

        Returns:
            题目信息字典
        """
        # 获取题目位置并转换为边界框
        pos_list = self._normalize_pos_list(subject.get("pos_list", []))
        question_bbox = None
        if pos_list:
            question_bbox = self._pos_to_bbox(pos_list)

        # 映射题目类型(根据阿里云官方文档)
        # 0:选择题 1:填空题 2:阅读理解 3:完型填空 4:阅读填空 5:问答题
        # 6:多选题 7:填空选择混合 8:应用题 9:判断题 10:作图题
        # 11:材料题 12:计算题 13:连线题 14:作文题 15:解答题 16:其他 17:图 18:表格
        type_mapping = {
            0: {"id": "choice", "name": "选择题"},
            1: {"id": "fill_blank", "name": "填空题"},
            2: {"id": "reading_comprehension", "name": "阅读理解"},
            3: {"id": "cloze", "name": "完型填空"},
            4: {"id": "reading_fill", "name": "阅读填空"},
            5: {"id": "answer", "name": "问答题"},
            6: {"id": "multiple_choice", "name": "多选题"},
            7: {"id": "mixed", "name": "填空选择混合"},
            8: {"id": "application", "name": "应用题"},
            9: {"id": "judge", "name": "判断题"},
            10: {"id": "drawing", "name": "作图题"},
            11: {"id": "material", "name": "材料题"},
            12: {"id": "calculation", "name": "计算题"},
            13: {"id": "matching", "name": "连线题"},
            14: {"id": "composition", "name": "作文题"},
            15: {"id": "solution", "name": "解答题"},
            16: {"id": "other", "name": "其他"},
            17: {"id": "figure", "name": "图"},
            18: {"id": "table", "name": "表格"},
        }
        
        question_text = subject.get("text", "")
        raw_type = subject.get("type", 0)
        type_info = type_mapping.get(raw_type, {"id": "unknown", "name": "未知题型"})
        question_type = type_info["id"]
        question_type_name = type_info["name"]
        
        question_id = f"{part_index}-{q_index}"
        if page_index is not None:
            question_id = f"{page_index}-{question_id}"
        question = {
            "id": question_id,
            "type": question_type,          # 英文标识
            "type_name": question_type_name,# 中文名称
            "raw_type": raw_type,           # 阿里云原始type类型值
            "prob": subject.get("prob", 1.0),                 # 识别置信度
            "num_choices": subject.get("num_choices", 0),     # 选项数量(如果有)
            "table_list": subject.get("table_list", []),      # 表格信息(如果有)
            "text": question_text,
            "position": question_bbox,
            "options": [],
            "answer_areas": [],
            "figures": [],
        }

        stem_texts = []
        for element in subject.get("element_list", []):
            element_type = element.get("type", 0)
            content_list = element.get("content_list", [])

            option_items = []
            pending_marker = ""
            for content in content_list:
                content_string = content.get("string", "").strip()
                if not content_string:
                    continue
                marker, text = self._split_option_content(content_string)
                if marker:
                    if not text or text == marker:
                        pending_marker = marker
                        continue
                    option_items.append((marker, text, content.get("pos", [])))
                    pending_marker = ""
                else:
                    if pending_marker:
                        option_items.append((pending_marker, content_string, content.get("pos", [])))
                        pending_marker = ""

            # 判断是否为选项：
            # 1. 明确标记为选项类型 (type=1)
            # 2. 或者在题干中找到了足够多的选项特征 (通过修复正则后, >=2 已经很安全)
            is_option_element = element_type == 1 or len(option_items) >= 2

            if is_option_element and option_items:
                for marker, text, pos in option_items:
                    question["options"].append(
                        {
                            "option": marker,
                            "text": text,
                            "position": self._pos_to_bbox(pos) if pos else None,
                        }
                    )
            elif element_type == 0:
                # 只有非选项元素的纯文本，才会被加入到题干组合里
                stem_texts.append(element.get("text", ""))

        if stem_texts:
            combined_text = "".join(stem_texts).strip()
            if combined_text:
                question["text"] = combined_text


        # 解析答案区域(统一使用边界框格式)
        for answer in subject.get("answer_list", []):
            if isinstance(answer, dict):
                pos = answer.get("pos", answer.get("pos_list", []))
            else:
                pos = answer
            pos_list = self._normalize_pos_list(pos)
            bbox = self._pos_to_bbox(pos_list) if pos_list else None
                
            if bbox:
                question["answer_areas"].append({"position": bbox})

        # 解析图片(去重并统一格式)
        seen_figures = set()  # 用于去重
        
        # 从 figure_list 提取
        for figure in subject.get("figure_list", []):
            if isinstance(figure, dict):
                pos = figure.get("pos", [])
            else:
                pos = figure

            pos_list = self._normalize_pos_list(pos)
            if pos_list:
                bbox = self._pos_to_bbox(pos_list)
                # 使用位置作为唯一标识去重
                fig_key = (bbox.get("x"), bbox.get("y"), bbox.get("width"), bbox.get("height"))
                if fig_key not in seen_figures:
                    seen_figures.add(fig_key)
                    question["figures"].append({"position": bbox})

        # 从顶层 figure 数组中匹配(只提取配图,排除题目整体截图)
        if question_bbox and all_figures:
            for figure in all_figures:
                fig_type = figure.get("type", "")
                if fig_type.startswith("subject_"):
                    fig_points = self._normalize_pos_list(figure.get("points", []))
                    if fig_points and self._is_figure_in_question(fig_points, question_bbox):
                        bbox = self._pos_to_bbox(fig_points)
                        fig_key = (bbox.get("x"), bbox.get("y"), bbox.get("width"), bbox.get("height"))
                        if fig_key not in seen_figures:
                            seen_figures.add(fig_key)
                            question["figures"].append({"position": bbox})

        return question

    def _is_figure_in_question(
        self, fig_points: List[Dict], question_bbox: Dict
    ) -> bool:
        """
        判断图片是否在题目范围内

        Args:
            fig_points: 图片坐标点
            question_bbox: 题目边界框

        Returns:
            是否在题目范围内
        """
        fig_points = self._normalize_pos_list(fig_points)
        if not fig_points or not question_bbox:
            return False

        fig_bbox = self._pos_to_bbox(fig_points)

        # 计算图片中心点
        fig_center_x = fig_bbox["x"] + fig_bbox["width"] / 2
        fig_center_y = fig_bbox["y"] + fig_bbox["height"] / 2

        # 判断中心点是否在题目范围内
        return (
            question_bbox["x"]
            <= fig_center_x
            <= question_bbox["x"] + question_bbox["width"]
            and question_bbox["y"]
            <= fig_center_y
            <= question_bbox["y"] + question_bbox["height"]
        )

    def _split_option_content(self, text: str):
        if not text:
            return "", ""
        text = text.strip()
        markers = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩"]
        if text in markers:
            return text, ""
        patterns = [
            r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*(.*)$",
            r"^(\([A-Za-z]\))\s*(.*)$",
            r"^(\([0-9]{1,2}\))\s*(.*)$",
            r"^([A-Z])(?:[、\)]|\.(?!\d))\s*(.*)$",
            r"^([a-z])(?:[、\)]|\.(?!\d))\s*(.*)$",
            r"^([A-Z])\s+(.*)$",
            r"^([a-z])\s+(.*)$",
            r"^([0-9]{1,2})(?:[、\)]|\.(?!\d))\s*(.*)$",
        ]
        import re

        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                marker = match.group(1)
                option_text = match.group(2).strip() or text
                return marker, option_text
        return "", ""

    def _normalize_pos_list(self, pos) -> List[Dict]:
        if not pos:
            return []
        if isinstance(pos, dict):
            return [pos]
        if isinstance(pos, list):
            if pos and isinstance(pos[0], dict):
                return pos
            flattened = []
            for item in pos:
                if isinstance(item, dict):
                    flattened.append(item)
                elif isinstance(item, list):
                    flattened.extend(self._normalize_pos_list(item))
            return flattened
        return []

    def _pos_to_bbox(self, pos: List[Dict]) -> Dict:
        """
        将坐标点列表转换为边界框

        Args:
            pos: 坐标点列表 [{'x': x1, 'y': y1}, ...]

        Returns:
            边界框 {'x': min_x, 'y': min_y, 'width': w, 'height': h}
        """
        pos = self._normalize_pos_list(pos)
        if not pos:
            return {}

        xs = [p["x"] for p in pos]
        ys = [p["y"] for p in pos]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}

    def _extract_question_images(
        self,
        parsed_result: Dict,
        source_image_path: str,
        output_dir: str,
        min_figure_area: int = 2000,
        extract_figures: bool = True,
        extract_answer_areas: bool = False,
    ) -> int:
        """
        提取题目中的图片

        Args:
            parsed_result: 解析后的结果(包含parts结构)
            source_image_path: 原始图片路径
            output_dir: 输出目录

        Returns:
            提取的图片数量
        """
        try:
            from PIL import Image
        except ImportError:
            print("⚠️  需要安装 Pillow: pip install Pillow")
            return 0

        os.makedirs(output_dir, exist_ok=True)
        extracted_count = 0

        with Image.open(source_image_path) as img:
            # 遍历所有部分和题目
            for part in parsed_result.get("parts", []):
                for question in part.get("questions", []):
                    q_id = question["id"]  # 使用新的全局唯一ID

                    if extract_figures:
                        for fig_idx, figure in enumerate(question.get("figures", []), 1):
                            bbox = figure.get("position")
                            area = 0
                            if bbox:
                                area = max(0, int(bbox.get("width", 0))) * max(
                                    0, int(bbox.get("height", 0))
                                )
                            if (
                                bbox
                                and bbox.get("width", 0) > 0
                                and bbox.get("height", 0) > 0
                                and area >= min_figure_area
                            ):
                                output_path = os.path.join(
                                    output_dir, f"q{q_id.replace('-', '_')}_figure_{fig_idx}.png"
                                )
                                self._crop_and_save(img, bbox, output_path)
                                figure["image_file"] = os.path.basename(output_path)
                                extracted_count += 1

                    if extract_answer_areas:
                        for area_idx, area in enumerate(question.get("answer_areas", []), 1):
                            bbox = area.get("position") if isinstance(area, dict) else None
                            if bbox and bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                                output_path = os.path.join(
                                    output_dir, f"q{q_id.replace('-', '_')}_answer_{area_idx}.png"
                                )
                                self._crop_and_save(img, bbox, output_path)
                                area["image_file"] = os.path.basename(output_path)
                                extracted_count += 1

        return extracted_count

    def _crop_and_save(self, img, bbox: Dict, output_path: str):
        """
        裁剪并保存图片

        Args:
            img: PIL Image 对象
            bbox: 边界框
            output_path: 输出路径
        """
        x = int(bbox["x"])
        y = int(bbox["y"])
        w = int(bbox["width"])
        h = int(bbox["height"])

        # PIL的crop使用(left, upper, right, lower)格式
        cropped = img.crop((x, y, x + w, y + h))
        cropped.save(output_path)

    def parse_baidu_questions(self, baidu_data: Dict) -> List[Dict]:
        questions = []
        qus_list = baidu_data.get("qus_result") or []
        for idx, qus in enumerate(qus_list, 1):
            pos_points = qus.get("qus_location", {}).get("points") or []
            bbox = self._pos_to_bbox(pos_points)
            q = {
                "id": f"b-{idx}",
                "type": qus.get("qus_type"),
                "text": "",
                "position": bbox,
                "options": [],
                "answer_areas": [],
            }
            elems = qus.get("qus_element") or []
            words = []
            for e in elems:
                e_words = e.get("elem_word") or []
                for w in e_words:
                    words.append(w)
                if e.get("elem_type") == "2":
                    e_pos = e.get("elem_location", {}).get("points") or []
                    eb = self._pos_to_bbox(e_pos)
                    if eb:
                        q["answer_areas"].append({"position": eb})
            full_text = []
            option_items = []
            pending_marker = ""
            for w in words:
                s = (w.get("word") or "").strip()
                if not s:
                    continue
                marker, text = self._split_option_content(s)
                wl = w.get("word_location") or {}
                wb = {
                    "x": int(wl.get("left", 0)),
                    "y": int(wl.get("top", 0)),
                    "width": int(wl.get("width", 0)),
                    "height": int(wl.get("height", 0)),
                }
                if marker:
                    if not text or text == marker:
                        pending_marker = marker
                        continue
                    option_items.append(
                        {"option": marker, "text": text, "position": wb}
                    )
                    pending_marker = ""
                else:
                    if pending_marker:
                        option_items.append(
                            {"option": pending_marker, "text": s, "position": wb}
                        )
                        pending_marker = ""
                    else:
                        full_text.append(s)
            q["text"] = " ".join(full_text).strip()
            q["options"] = option_items
            questions.append(q)
        return questions

    def merge_with_baidu(self, ali_parts: Dict, baidu_questions: List[Dict]) -> Dict:
        def center(b):
            return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        def contains(b, cx, cy):
            return b and (b["x"] <= cx <= b["x"] + b["width"] and b["y"] <= cy <= b["y"] + b["height"])
        for part in ali_parts.get("parts", []):
            for q in part.get("questions", []):
                qb = q.get("position")
                if not qb:
                    continue
                cx, cy = center(qb)
                candidates = []
                for bq in baidu_questions:
                    bp = bq.get("position")
                    if bp and contains(bp, cx, cy):
                        candidates.append(bq)
                if not candidates:
                    continue
                bq = candidates[0]
                if not q.get("options"):
                    q["options"] = bq.get("options", [])
                else:
                    need_fill = any((not o.get("text") or o.get("text") == o.get("option")) for o in q["options"])
                    if need_fill and bq.get("options"):
                        q["options"] = bq["options"]
                if not q.get("text"):
                    q["text"] = bq.get("text", q.get("text", ""))
                if not q.get("answer_areas"):
                    q["answer_areas"] = bq.get("answer_areas", [])
        return ali_parts
    def _list_image_files(self, input_dir: str) -> List[str]:
        """
        列出目录中的所有图片文件

        Args:
            input_dir: 输入目录

        Returns:
            图片文件路径列表
        """
        input_path = Path(input_dir)
        if not input_path.is_dir():
            raise ValueError(f"目录不存在: {input_dir}")

        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}

        image_files = [
            str(path)
            for path in sorted(input_path.iterdir())
            if path.is_file() and path.suffix.lower() in image_extensions
        ]

        return image_files
