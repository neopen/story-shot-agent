"""
@FileName: script_assessor_tool.py
@Description: 剧本评估工具，评估剧本质量并提供改进建议
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18 23:33
"""
import hashlib
import math
import re
from typing import List, Dict

import numpy as np


class ComplexityAssessor:
    """剧本复杂度评估器 - 完整版"""

    def assess_complexity(self, text: str) -> float:
        """
        主复杂度评估函数（0-1，越高越复杂）
        """
        if not text or not text.strip():
            return 0.0

        text = text.strip()

        # 1. 计算各个维度的复杂度
        dimensions = {
            "structural": self._structural_complexity(text),
            "semantic": self._semantic_complexity(text),
            "character": self._character_complexity(text),
            "temporal": self._temporal_complexity(text),
            "emotional": self._emotional_complexity(text),
            "narrative": self._narrative_complexity(text)  # 新增：叙事复杂度
        }

        # 2. 计算维度权重（可配置）
        weights = {
            "structural": 0.15,  # 结构
            "semantic": 0.15,  # 语义
            "character": 0.20,  # 角色
            "temporal": 0.15,  # 时间
            "emotional": 0.20,  # 情感
            "narrative": 0.15  # 叙事
        }

        # 3. 加权计算总分
        total_score = 0.0
        for dimension, score in dimensions.items():
            weight = weights.get(dimension, 0.15)  # 默认权重
            total_score += score * weight

        # 4. 考虑长度因素（长文本通常更复杂）
        length_factor = self._calculate_length_factor(text)
        total_score *= length_factor

        # 5. 考虑格式复杂度
        format_complexity = self._assess_format_complexity(text)
        total_score = (total_score * 0.8) + (format_complexity * 0.2)

        # 6. 归一化到0-1范围
        final_score = min(1.0, max(0.0, total_score))

        # 7. 缓存结果（可选）
        self._last_assessment = {
            "text_hash": hashlib.md5(text.encode()).hexdigest()[:8],
            "dimensions": dimensions,
            "weights": weights,
            "length_factor": length_factor,
            "format_complexity": format_complexity,
            "final_score": final_score
        }

        return final_score

    def _calculate_length_factor(self, text: str) -> float:
        """
        计算文本长度影响因子
        """
        char_count = len(text)
        word_count = len(re.findall(r'[\u4e00-\u9fa5]+', text))

        # 基于字符数的长度因子
        if char_count < 100:
            char_factor = 0.5  # 很短
        elif char_count < 500:
            char_factor = 0.7  # 短
        elif char_count < 2000:
            char_factor = 0.9  # 中等
        elif char_count < 5000:
            char_factor = 1.0  # 长
        else:
            char_factor = 1.1  # 很长

        # 基于词数的长度因子
        if word_count < 50:
            word_factor = 0.6
        elif word_count < 200:
            word_factor = 0.8
        elif word_count < 500:
            word_factor = 0.95
        elif word_count < 1000:
            word_factor = 1.0
        else:
            word_factor = 1.05

        # 取平均值，但不超过1.2
        return min(1.2, (char_factor + word_factor) / 2)

    def _narrative_complexity(self, text: str) -> float:
        """
        评估叙事复杂度
        """
        # 1. 视角变化
        perspective_changes = self._count_perspective_changes(text)

        # 2. 叙事层次（对话、描述、内心独白等）
        narrative_layers = self._count_narrative_layers(text)

        # 3. 悬念设置
        suspense_density = self._assess_suspense_density(text)

        # 4. 情节转折
        plot_twists = self._count_plot_twists(text)

        # 综合评分
        perspective_score = min(1.0, perspective_changes / 5)  # 最多5次视角变化
        layers_score = min(1.0, narrative_layers / 4)  # 最多4层叙事
        suspense_score = min(1.0, suspense_density / 3)  # 悬念密度
        twist_score = min(1.0, plot_twists / 3)  # 最多3次情节转折

        return (perspective_score * 0.25 +
                layers_score * 0.25 +
                suspense_score * 0.30 +
                twist_score * 0.20)

    def _count_perspective_changes(self, text: str) -> int:
        """
        计算视角变化次数
        """
        # 视角关键词
        perspective_indicators = {
            "first_person": ["我", "我们", "本人", "咱"],
            "third_person": ["他", "她", "他们", "她们", "某人"],
            "narrative": ["故事", "传说", "据说", "相传"],
            "omniscient": ["此时", "此刻", "这时", "突然", "原来"]
        }

        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 2:
            return 0

        # 为每个句子标注主要视角
        sentence_perspectives = []
        for sentence in sentences:
            perspective_counts = {key: 0 for key in perspective_indicators.keys()}

            for persp_type, keywords in perspective_indicators.items():
                for keyword in keywords:
                    if keyword in sentence:
                        perspective_counts[persp_type] += 1

            # 确定主要视角
            if sum(perspective_counts.values()) == 0:
                main_perspective = "neutral"
            else:
                main_perspective = max(perspective_counts.items(), key=lambda x: x[1])[0]

            sentence_perspectives.append(main_perspective)

        # 计算视角变化次数
        changes = 0
        for i in range(1, len(sentence_perspectives)):
            if sentence_perspectives[i] != sentence_perspectives[i - 1]:
                changes += 1

        return changes

    def _count_narrative_layers(self, text: str) -> int:
        """
        计算叙事层次数量
        """
        layers_found = set()

        # 1. 外部描述
        if self._has_external_description(text):
            layers_found.add("external_description")

        # 2. 对话
        dialogue_patterns = [r'["「](.+?)["」]', r'([^：:]+)[：:]["「](.+?)["」]']
        for pattern in dialogue_patterns:
            if re.search(pattern, text):
                layers_found.add("dialogue")
                break

        # 3. 内心独白
        inner_monologue_indicators = ["心想", "暗想", "寻思", "琢磨", "觉得", "感到", "意识到"]
        if any(indicator in text for indicator in inner_monologue_indicators):
            layers_found.add("inner_monologue")

        # 4. 回忆/闪回
        flashback_indicators = ["回忆", "想起", "回想", "记得", "当年", "从前", "过去"]
        if any(indicator in text for indicator in flashback_indicators):
            layers_found.add("flashback")

        # 5. 旁白/解说
        narration_indicators = ["话说", "却说", "且说", "原来", "其实", "实际上"]
        if any(indicator in text for indicator in narration_indicators):
            layers_found.add("narration")

        return len(layers_found)

    def _has_external_description(self, text: str) -> bool:
        """判断是否有外部描述"""
        descriptive_keywords = ["天空", "大地", "房间", "街道", "建筑", "环境", "氛围", "气氛"]
        return any(keyword in text for keyword in descriptive_keywords)

    def _assess_suspense_density(self, text: str) -> float:
        """
        评估悬念密度
        """
        suspense_indicators = [
            "突然", "猛地", "意外", "惊奇", "惊讶", "震惊",
            "没想到", "不料", "谁知", "竟然", "居然",
            "秘密", "谜", "疑惑", "疑问", "不解",
            "紧张", "恐惧", "害怕", "担心", "忧虑",
            "悬念", "悬疑", "未知", "不明", "神秘"
        ]

        total_sentences = len(re.split(r'[。！？]', text))
        if total_sentences == 0:
            return 0.0

        # 统计包含悬念词的句子
        suspense_sentences = 0
        sentences = re.split(r'[。！？]', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if any(indicator in sentence for indicator in suspense_indicators):
                suspense_sentences += 1

        # 计算密度
        density = suspense_sentences / total_sentences
        return min(1.0, density * 5)  # 乘以5使值域更合理

    def _count_plot_twists(self, text: str) -> int:
        """
        计算情节转折次数
        """
        plot_twist_indicators = [
            "但是", "然而", "可是", "却", "不过",
            "突然", "意外地", "没想到", "不料", "谁知",
            "原来", "其实", "实际上", "真相是",
            "反转", "转折", "变化", "转变"
        ]

        twist_count = 0
        sentences = re.split(r'[。！？]', text)

        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue

            # 检查是否包含转折词
            for indicator in plot_twist_indicators:
                if indicator in sentence:
                    twist_count += 1
                    break

        return min(5, twist_count)  # 最多计5次

    def _assess_format_complexity(self, text: str) -> float:
        """
        评估格式复杂度
        """
        lines = text.strip().split('\n')
        if not lines:
            return 0.0

        # 1. 格式类型数量
        format_types = set()
        line_type_counts = {}

        for line in lines[:50]:  # 只检查前50行
            line = line.strip()
            if not line:
                continue

            line_type = self._classify_line_format(line)
            format_types.add(line_type)
            line_type_counts[line_type] = line_type_counts.get(line_type, 0) + 1

        # 2. 格式混合程度
        total_lines = sum(line_type_counts.values())
        if total_lines == 0:
            return 0.0

        # 计算香农熵作为混合程度指标
        entropy = 0.0
        for count in line_type_counts.values():
            probability = count / total_lines
            if probability > 0:
                entropy -= probability * math.log2(probability)

        # 3. 特殊格式标记
        special_format_score = 0.0
        special_patterns = [
            r'^#+',  # Markdown标题
            r'^\d+\.',  # 数字列表
            r'^[-*]',  # 项目符号
            r'^>',  # 引用
            r'^```',  # 代码块
            r'^\[.*\]\(.*\)',  # 链接
        ]

        for line in lines[:30]:
            for pattern in special_patterns:
                if re.match(pattern, line.strip()):
                    special_format_score += 0.1
                    break

        # 综合评分
        type_score = min(1.0, len(format_types) / 6)  # 最多6种类型
        entropy_score = min(1.0, entropy / 2)  # 熵的最大值约2
        special_score = min(0.3, special_format_score)  # 特殊格式最多贡献0.3

        return type_score * 0.4 + entropy_score * 0.4 + special_score * 0.2

    def _classify_line_format(self, line: str) -> str:
        """分类行格式类型"""
        if re.match(r'^\[.*]', line):
            return "time_marker"
        elif re.match(r'^(INT\.|EXT\.)', line):
            return "scene_header"
        elif re.match(r'^[A-Z][A-Z\s]+$', line) and len(line) < 30:
            return "character_name"
        elif '"' in line or '「' in line:
            return "dialogue_line"
        elif re.match(r'^\s{4,}', line) or re.match(r'^\t', line):
            return "indented"
        elif any(marker in line for marker in ['：', ':', '场景', '地点', '时间', '人物']):
            return "field_label"
        elif len(line) < 60 and not any(punct in line for punct in '。！？'):
            return "short_action"
        elif any(num in line for num in '一二三四五六七八九十1234567890') and '、' in line:
            return "numbered_list"
        else:
            return "description"

    def _structural_complexity(self, text: str) -> float:
        """结构复杂度"""
        lines = text.strip().split('\n')

        # 1. 段落/场景数量
        paragraph_count = len([l for l in lines if l.strip()])
        if paragraph_count <= 5:
            para_score = 0.2
        elif paragraph_count <= 10:
            para_score = 0.5
        else:
            para_score = 0.8

        # 2. 格式多样性
        format_variety = self._detect_format_variety(text)

        # 3. 嵌套深度
        nesting_depth = self._calculate_nesting_depth(text)

        # 综合
        return (para_score * 0.4 + format_variety * 0.3 + nesting_depth * 0.3)

    def _semantic_complexity(self, text: str) -> float:
        """语义复杂度"""
        # 1. 词汇多样性
        words = re.findall(r'[\u4e00-\u9fa5]+', text)
        unique_words = set(words)
        word_variety = len(unique_words) / max(len(words), 1)

        # 2. 句子长度差异
        sentences = re.split(r'[。！？；;]', text)
        sent_lengths = [len(s.strip()) for s in sentences if s.strip()]
        if sent_lengths:
            length_std = np.std(sent_lengths) / np.mean(sent_lengths) if np.mean(sent_lengths) > 0 else 0
        else:
            length_std = 0

        # 3. 抽象概念比例
        abstract_ratio = self._calculate_abstract_ratio(text)

        return min(1.0, word_variety * 0.4 + length_std * 0.3 + abstract_ratio * 0.3)

    def _character_complexity(self, text: str) -> float:
        """角色复杂度"""
        # 1. 角色数量
        characters = self._extract_character_names(text)
        char_count = len(characters)

        if char_count <= 2:
            count_score = 0.2
        elif char_count <= 5:
            count_score = 0.5
        else:
            count_score = 0.8

        # 2. 角色交互密度
        interaction_density = self._calculate_interaction_density(text, characters)

        # 3. 角色描述复杂度
        description_complexity = self._assess_character_descriptions(text)

        return min(1.0, count_score * 0.4 + interaction_density * 0.4 + description_complexity * 0.2)

    def _assess_character_descriptions(self, text: str) -> float:
        """
        评估角色描述复杂度
        """
        # 1. 提取角色描述片段
        character_descriptions = self._extract_character_description_segments(text)

        if not character_descriptions:
            return 0.2  # 无详细描述，复杂度低

        # 2. 计算平均描述长度
        desc_lengths = [len(desc) for desc in character_descriptions]
        avg_length = sum(desc_lengths) / len(desc_lengths)

        # 3. 描述多样性（使用了多少不同的描述维度）
        description_dimensions = self._count_description_dimensions(character_descriptions)

        # 4. 详细程度评分
        length_score = min(1.0, avg_length / 50)  # 平均50字为上限

        # 5. 维度评分（0-1）
        dimension_score = min(1.0, description_dimensions / 6)  # 最多6个维度

        # 综合评分
        return length_score * 0.6 + dimension_score * 0.4

    def _extract_character_description_segments(self, text: str) -> List[str]:
        """
        从文本中提取角色描述片段
        """
        descriptions = []

        # 模式1: "角色名（年龄）描述"
        pattern1 = r'([\u4e00-\u9fa5]{2,4})（[\u4e00-\u9fa5\d]+?）([^。！？]+[。！？])'
        matches1 = re.findall(pattern1, text)
        for match in matches1:
            if len(match) >= 3:
                descriptions.append(match[2])

        # 模式2: "角色名，描述"
        pattern2 = r'([\u4e00-\u9fa5]{2,4})[，、]([^。！？]+[。！？])'
        matches2 = re.findall(pattern2, text)
        for match in matches2:
            if len(match) >= 2:
                # 检查是否是真正的描述（而不是对话或其他）
                desc_text = match[1]
                if self._is_likely_description(desc_text):
                    descriptions.append(desc_text)

        # 模式3: 包含"穿着"、"戴着"、"留着"等描述词的句子
        desc_keywords = ["穿着", "戴着", "留着", "有着", "长着", "身材", "面容", "眼神"]
        sentences = re.split(r'[。！？]', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if any(keyword in sentence for keyword in desc_keywords):
                # 检查句子中是否有角色名
                if self._contains_character_name(sentence):
                    descriptions.append(sentence)

        return descriptions

    def _count_description_dimensions(self, descriptions: List[str]) -> int:
        """
        计算角色描述的维度数量
        """
        dimension_categories = {
            "appearance": ["穿着", "衣服", "服装", "打扮", "外套", "裙子", "裤子"],
            "physique": ["身材", "身高", "体型", "瘦", "胖", "强壮", "娇小"],
            "face": ["面容", "脸庞", "脸", "相貌", "五官", "眼睛", "鼻子", "嘴巴"],
            "hair": ["头发", "发型", "短发", "长发", "卷发", "直发", "发色"],
            "accessories": ["戴着", "拿着", "提着", "背着", "挎着", "佩戴"],
            "expression": ["表情", "神色", "眼神", "目光", "笑容", "皱眉"],
            "age_hint": ["年轻", "年老", "中年", "少年", "老年", "青春"],
            "gender_hint": ["英俊", "帅气", "美丽", "漂亮", "妩媚", "阳刚"]
        }

        dimensions_found = set()

        for desc in descriptions:
            for category, keywords in dimension_categories.items():
                if any(keyword in desc for keyword in keywords):
                    dimensions_found.add(category)

        return len(dimensions_found)

    def _temporal_complexity(self, text: str) -> float:
        """时间复杂度"""
        # 1. 时间变化次数
        time_keywords = ["清晨", "早晨", "上午", "中午", "下午", "傍晚", "夜晚", "深夜",
                         "第二天", "三天后", "一周后", "突然", "然后", "接着", "随后"]

        time_changes = 0
        for keyword in time_keywords:
            time_changes += text.count(keyword)

        if time_changes <= 2:
            change_score = 0.2
        elif time_changes <= 5:
            change_score = 0.5
        else:
            change_score = 0.8

        # 2. 时间跳跃幅度
        time_jump_score = self._assess_time_jumps(text)

        return min(1.0, change_score * 0.6 + time_jump_score * 0.4)

    def _emotional_complexity(self, text: str) -> float:
        """情感复杂度"""
        # 情感关键词库
        emotion_keywords = {
            "positive": ["高兴", "快乐", "兴奋", "喜悦", "幸福", "满意", "感动"],
            "negative": ["悲伤", "痛苦", "愤怒", "失望", "恐惧", "焦虑", "绝望"],
            "intense": ["大哭", "怒吼", "尖叫", "狂喜", "崩溃", "震惊"]
        }

        # 1. 情感种类
        emotion_types = set()
        for category, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    emotion_types.add(category)

        type_score = len(emotion_types) / 3.0  # 最多3种

        # 2. 情感强度
        intense_count = sum(text.count(keyword) for keyword in emotion_keywords["intense"])
        intensity_score = min(1.0, intense_count / 5.0)  # 5次强烈情感为上限

        # 3. 情感变化
        emotion_changes = self._count_emotion_changes(text, emotion_keywords)
        change_score = min(1.0, emotion_changes / 10.0)  # 10次变化为上限

        return type_score * 0.3 + intensity_score * 0.4 + change_score * 0.3

    def _detect_format_variety(self, text: str) -> float:
        """检测格式多样性"""
        lines = text.strip().split('\n')

        # 检测不同的行类型
        line_types = set()
        for line in lines[:20]:  # 只检查前20行
            line = line.strip()
            if not line:
                continue

            if re.match(r'^\[.*]', line):
                line_types.add("time_marker")
            elif re.match(r'^(INT\.|EXT\.)', line):
                line_types.add("scene_header")
            elif re.match(r'^[A-Z][A-Z\s]+$', line):
                line_types.add("character_name")
            elif '：' in line or ':' in line:
                line_types.add("field_label")
            elif '"' in line or '「' in line:
                line_types.add("dialogue")
            elif len(line) < 50 and not any(punct in line for punct in '。！？'):
                line_types.add("short_action")
            else:
                line_types.add("description")

        # 格式多样性评分
        type_count = len(line_types)
        return min(1.0, type_count / 6.0)  # 最多6种类型

    def _calculate_nesting_depth(self, text: str) -> float:
        """计算嵌套深度（如括号嵌套）"""
        max_depth = 0
        current_depth = 0

        for char in text:
            if char in '（「([':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char in '）」)]':
                current_depth = max(0, current_depth - 1)

        return min(1.0, max_depth / 5.0)  # 最大深度5为上限

    def _calculate_abstract_ratio(self, text: str) -> float:
        """计算抽象概念比例"""
        abstract_terms = ["思考", "回忆", "想象", "感觉", "认为", "相信", "希望",
                          "梦想", "未来", "过去", "心灵", "灵魂", "情感", "命运"]

        concrete_terms = ["走", "跑", "坐", "站", "拿", "放", "开", "关",
                          "桌子", "椅子", "房间", "街道", "汽车", "手机"]

        abstract_count = sum(text.count(term) for term in abstract_terms)
        concrete_count = sum(text.count(term) for term in concrete_terms)

        total = abstract_count + concrete_count
        if total == 0:
            return 0.0

        return abstract_count / total

    def _extract_character_names(self, text: str) -> List[str]:
        """提取角色名"""
        # 中文名模式（2-4个汉字）
        name_pattern = r'([\u4e00-\u9fa5]{2,4})（[\u4e00-\u9fa5]+?）|([\u4e00-\u9fa5]{2,4})[：:]["「]'

        names = set()
        matches = re.findall(name_pattern, text)
        for match in matches:
            for name in match:
                if name and len(name.strip()) >= 2:
                    names.add(name.strip())

        # 英文名模式（大写字母开头）
        english_pattern = r'\b[A-Z][a-z]+\b'
        english_matches = re.findall(english_pattern, text)
        names.update(english_matches)

        return list(names)

    def _calculate_interaction_density(self, text: str, characters: List[str]) -> float:
        """计算角色交互密度"""
        if len(characters) < 2:
            return 0.0

        # 统计对话交替次数
        dialogue_patterns = [
            r'([\u4e00-\u9fa5]{2,4})[：:]["「](.+?)["」]',
            r'["「](.+?)["」][（(]([\u4e00-\u9fa5]{2,4})[）)]'
        ]

        all_speakers = []
        for pattern in dialogue_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) >= 2:
                    speaker = match[0] if match[0] else match[1]
                    all_speakers.append(speaker)

        # 计算发言者变化次数
        if len(all_speakers) < 2:
            return 0.0

        changes = 0
        for i in range(1, len(all_speakers)):
            if all_speakers[i] != all_speakers[i - 1]:
                changes += 1

        return min(1.0, changes / len(all_speakers))

    def _assess_time_jumps(self, text: str) -> float:
        """
        评估时间跳跃的复杂度
        """
        # 时间相关关键词
        time_indicators = {
            "immediate": ["突然", "猛地", "立刻", "马上", "瞬间", "刹那间"],
            "short": ["片刻", "一会儿", "几分钟后", "片刻之后", "不久"],
            "medium": ["随后", "接着", "然后", "过后", "之后"],
            "long": ["第二天", "三天后", "一周后", "一个月后", "几年后", "多年后"],
            "vague": ["后来", "某天", "有一天", "曾经", "过去", "从前"],
            "flashback": ["回忆", "想起", "回想", "记忆", "往事", "当年"],
            "time_of_day": ["清晨", "早晨", "上午", "中午", "下午", "傍晚", "夜晚", "深夜"]
        }

        # 统计各类时间指示词的出现次数
        counts = {}
        for category, keywords in time_indicators.items():
            count = sum(text.count(keyword) for keyword in keywords)
            counts[category] = count

        total_time_indicators = sum(counts.values())

        if total_time_indicators == 0:
            return 0.1  # 几乎没有时间指示，复杂度低

        # 计算时间跳跃复杂度
        jump_complexity = 0.0

        # 1. 长时跳跃比例
        long_jump_ratio = counts["long"] / total_time_indicators if total_time_indicators > 0 else 0
        jump_complexity += long_jump_ratio * 0.3

        # 2. 闪回比例
        flashback_ratio = counts["flashback"] / total_time_indicators if total_time_indicators > 0 else 0
        jump_complexity += flashback_ratio * 0.4  # 闪回对复杂度影响更大

        # 3. 模糊时间比例
        vague_ratio = counts["vague"] / total_time_indicators if total_time_indicators > 0 else 0
        jump_complexity += vague_ratio * 0.3

        # 4. 时间变化频率（相邻句子的时间变化）
        time_change_frequency = self._calculate_time_change_frequency(text, time_indicators)
        jump_complexity += time_change_frequency * 0.2

        # 限制在0-1范围内
        return min(1.0, jump_complexity)

    def _calculate_time_change_frequency(self, text: str, time_indicators: Dict) -> float:
        """
        计算时间变化的频率
        """
        # 将文本分割为句子
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 2:
            return 0.0

        # 为每个句子提取时间标签
        sentence_time_tags = []
        for sentence in sentences:
            tags = set()
            for category, keywords in time_indicators.items():
                if any(keyword in sentence for keyword in keywords):
                    tags.add(category)

            # 如果没有明确时间标签，标记为"neutral"
            if not tags:
                tags.add("neutral")

            sentence_time_tags.append(tags)

        # 计算相邻句子时间变化的次数
        time_changes = 0
        for i in range(1, len(sentence_time_tags)):
            prev_tags = sentence_time_tags[i - 1]
            curr_tags = sentence_time_tags[i]

            # 如果两组标签完全不同，计为时间变化
            if prev_tags != curr_tags and not (prev_tags == {"neutral"} and curr_tags == {"neutral"}):
                time_changes += 1

        # 归一化到0-1
        max_possible_changes = len(sentences) - 1
        return time_changes / max_possible_changes if max_possible_changes > 0 else 0.0

    def _count_emotion_changes(self, text: str, emotion_keywords: Dict) -> int:
        """
        计算情感变化的次数
        """
        # 将文本分割为句子
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 2:
            return 0

        # 为每个句子标注情感
        sentence_emotions = []
        for sentence in sentences:
            emotions = set()

            # 检查每个情感类别
            for category, keywords in emotion_keywords.items():
                if any(keyword in sentence for keyword in keywords):
                    emotions.add(category)

            # 如果没有明确情感，标记为"neutral"
            if not emotions:
                emotions.add("neutral")

            sentence_emotions.append(emotions)

        # 计算情感变化次数
        emotion_changes = 0
        for i in range(1, len(sentence_emotions)):
            prev_emotions = sentence_emotions[i - 1]
            curr_emotions = sentence_emotions[i]

            # 如果情感集合发生变化，计为一次情感变化
            if prev_emotions != curr_emotions:
                emotion_changes += 1

        return emotion_changes

    def _is_likely_description(self, text: str) -> bool:
        """
        判断文本是否可能是描述性内容
        """
        # 描述性文本的特征
        descriptive_indicators = ["穿着", "戴着", "留着", "有着", "长着",
                                  "身材", "面容", "眼神", "大约", "看起来"]

        # 非描述性文本的特征（对话、动作等）
        non_descriptive_indicators = ["说", "道", "问", "喊", "叫", "走", "跑",
                                      "坐", "站", "拿", "放", "开", "关"]

        desc_score = sum(1 for indicator in descriptive_indicators if indicator in text)
        non_desc_score = sum(1 for indicator in non_descriptive_indicators if indicator in text)

        return desc_score > non_desc_score

    def _contains_character_name(self, text: str) -> bool:
        """
        判断文本中是否包含角色名
        """
        # 简单模式：2-4个中文字符，可能出现在括号前
        name_pattern = r'([\u4e00-\u9fa5]{2,4})（|([\u4e00-\u9fa5]{2,4})[，：:]'

        return bool(re.search(name_pattern, text))
