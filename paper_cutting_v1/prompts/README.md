# 试卷结构化提示词库

## 目录结构

```
prompts/
├── exam-paper-base/          # 基础通用提示词（所有学段学科通用）
│   └── base.md              
├── primary/                  # 小学
│   ├── chinese/             
│   │   └── prompt.md        # 语文专项（包含小学语文特有规则）
│   ├── math/                
│   │   └── prompt.md        # 数学专项（包含小学数学特有规则）
│   ├── english/             
│   │   └── prompt.md        # 英语专项（待完善）
│   └── science/             
│       └── prompt.md        # 科学专项（待完善）
├── junior/                   # 初中
│   ├── chinese/             
│   ├── math/                
│   ├── english/             
│   ├── physics/             
│   └── chemistry/           
└── senior/                   # 高中
    ├── chinese/             
    ├── math/                
    └── english/             
```

## 使用方式

### 1. 组合提示词
处理试卷时，按以下顺序组合提示词：
```
基础提示词 + 学科提示词 + OCR内容
```

例如，处理小学数学试卷：
```python
base_prompt = read_file("exam-paper-base/base.md")
subject_prompt = read_file("primary/math/prompt.md")
final_prompt = base_prompt + "\n\n" + subject_prompt + "\n\n" + ocr_content
```

例如，处理小学语文试卷：
```python
base_prompt = read_file("exam-paper-base/base.md")
subject_prompt = read_file("primary/chinese/prompt.md")
final_prompt = base_prompt + "\n\n" + subject_prompt + "\n\n" + ocr_content
```

### 2. 提示词内容
- **基础提示词**（exam-paper-base/base.md）：所有学段学科通用的规则
- **学科提示词**：该学科特有的规则和示例

### 3. 扩展方式
添加新学科时：
1. 在对应学段目录下创建学科文件夹
2. 创建 `prompt.md` 文件
3. 参考现有格式编写提示词

## 提示词编写规范

### 必须包含的内容
1. **学科特点**：简要说明该学科试卷的特点
2. **题型识别规则**：列出常见题型及识别方法
3. **特殊处理**：说明该学科特有的处理规则
4. **示例**：提供具体的拆分示例

### 编写原则
- 简洁明了，避免冗余
- 突出学科特色
- 注重实用性
- 不要重复基础提示词的内容

## 已完成的提示词

### 1. 基础通用（exam-paper-base/base.md）
- LaTeX 格式保留
- 题目拆分规则
- 图片处理
- JSON 结构
- 题型识别
- 输出要求

### 2. 小学语文（primary/chinese/prompt.md）
- 拼音题处理
- 字词题、句子题
- 阅读理解题（重点）
- 看图写话/作文题
- 填空框图片处理
- 拼音格式保留
- 古诗文处理

### 3. 小学数学（primary/math/prompt.md）
- 计算题处理（口算、笔算、脱式）
- 填空题（符号填空、情景填空）
- 选择题
- 应用题（多问拆分）
- 判断题
- 操作题
- LaTeX 格式保留（重点）
- 图形题的图片处理

## 注意事项

1. **基础提示词**包含所有学科通用的规则，学科提示词只需补充特有规则
2. **保持格式统一**，便于程序读取和组合
3. **及时更新**，根据实际使用情况优化提示词
4. **所有文件使用 .md 格式**，便于编辑和维护
