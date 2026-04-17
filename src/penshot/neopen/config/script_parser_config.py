"""
@FileName: script_parser_config.py
@Description: 剧本转换智能体配置
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/10/27 17:22
"""
import os
import re
from typing import Optional, Dict, List, Any

import yaml

from penshot.neopen.config.base_config import BaseConfig
from penshot.logger import debug, warning, error
from penshot.neopen.shot_language import ShotLanguage

class ScriptParserConfig(BaseConfig):
    """剧本解析器配置类"""
    
    def _initialize_config(self, language: ShotLanguage = ShotLanguage.ZH):
        """初始化配置类
        
        Args:
            language: 语言代码，如'zh'或'en'，默认使用系统设置的语言
        """
        # 加载的配置
        self._config = {}
        
        # 场景类型配置
        self.scene_types = self.DEFAULT_SCENE_TYPES.copy()
        
        # 配置缓存，避免频繁加载
        self._config_cache = {}
        self._last_config_update = {}

        self._language = language

    def _config_file_name(self) -> str:
        """配置文件名"""
        return 'script_parser_config.yaml'

    def _get_cached_config(self, config_filename: str = 'script_parser_config.yaml') -> Dict[str, Any]:
        """获取缓存的配置，如果缓存不存在或已过期则重新加载
        
        Args:
            config_filename: 配置文件名
            
        Returns:
            配置数据字典
        """
        import os
        import time
        
        # 根据语言生成唯一的缓存键
        cache_key = f"{self._language}_{config_filename}"
        
        # 检查缓存是否存在
        if cache_key in self._config_cache:
            # 根据语言选择配置文件路径
            if self._language == ShotLanguage.EN:
                # 英文配置文件放在en子目录下
                config_path = os.path.join(os.path.dirname(__file__), 'en', f'{config_filename}')
            else:
                # 中文配置文件放在zh子目录下
                config_path = os.path.join(os.path.dirname(__file__), 'zh', config_filename)
            
            if os.path.exists(config_path):
                current_mtime = os.path.getmtime(config_path)
                # 如果文件未被修改且缓存时间小于5分钟，则使用缓存
                if (cache_key in self._last_config_update and 
                    current_mtime == self._last_config_update[cache_key] and 
                    time.time() - self._last_config_update.get(f"{cache_key}_time", 0) < 300):
                    return self._config_cache[cache_key]
        
        # 重新加载配置
        config_data = self.load_yaml_config(config_filename)
        
        # 更新缓存
        self._config_cache[cache_key] = config_data
        
        # 更新缓存时间和文件修改时间
        if self._language == ShotLanguage.EN:
            config_path = os.path.join(os.path.dirname(__file__), 'en', f'{config_filename}')
        else:
            config_path = os.path.join(os.path.dirname(__file__), 'zh', config_filename)
            
        if os.path.exists(config_path):
            self._last_config_update[cache_key] = os.path.getmtime(config_path)
        self._last_config_update[f"{cache_key}_time"] = time.time()
        
        return config_data
    
    def load_config(self, config_data: Dict[str, Any]):
        """加载配置数据
        
        Args:
            config_data: 配置数据字典
        """
        self._config = config_data.copy()
        
        # 处理新的配置结构 (parse_rules)
        if "parse_rules" in config_data:
            parse_rules = config_data["parse_rules"]
            
            # 处理场景识别规则
            if "scene_recognition" in parse_rules:
                scene_recog = parse_rules["scene_recognition"]
                # 合并场景相关的模式
                all_scene_patterns = []
                if "start_patterns" in scene_recog:
                    all_scene_patterns.extend(scene_recog["start_patterns"])
                if "transition_patterns" in scene_recog:
                    all_scene_patterns.extend(scene_recog["transition_patterns"])
                if "end_patterns" in scene_recog:
                    all_scene_patterns.extend(scene_recog["end_patterns"])
                if all_scene_patterns:
                    self._config["scene_patterns"] = all_scene_patterns
            
            # 处理角色识别规则
            if "character_recognition" in parse_rules:
                char_recog = parse_rules["character_recognition"]
                if "name_patterns" in char_recog:
                    # 将角色名提取模式作为对话模式的一部分
                    self._config["dialogue_patterns"] = char_recog["name_patterns"]
            
            # 处理对话识别规则
            if "dialogue_recognition" in parse_rules:
                dial_recog = parse_rules["dialogue_recognition"]
                all_dialogue_patterns = []
                if "direct_patterns" in dial_recog:
                    all_dialogue_patterns.extend(dial_recog["direct_patterns"])
                if "indirect_patterns" in dial_recog:
                    all_dialogue_patterns.extend(dial_recog["indirect_patterns"])
                if all_dialogue_patterns:
                    # 如果有角色名模式和对话模式，合并它们
                    if "dialogue_patterns" in self._config:
                        self._config["dialogue_patterns"].extend(all_dialogue_patterns)
                    else:
                        self._config["dialogue_patterns"] = all_dialogue_patterns
            
            # 处理情绪识别规则
            if "emotion_recognition" in parse_rules and "keywords" in parse_rules["emotion_recognition"]:
                emotion_keywords = parse_rules["emotion_recognition"]["keywords"]
                # 转换为情绪关键词映射
                emotion_map = {}
                for emotion_type, words in emotion_keywords.items():
                    if isinstance(words, list):
                        emotion_map[emotion_type] = words
                if emotion_map:
                    self._config["emotion_keywords"] = emotion_map
        
        # 处理场景特殊规则
        if "scene_special_rules" in config_data:
            # 初始化场景特殊规则到手机场景配置
            phone_action_patterns = []
            for rule in config_data["scene_special_rules"]:
                if "pattern" in rule and isinstance(rule, dict):
                    phone_action_patterns.append({
                        "pattern": rule["pattern"],
                        "description": rule.get("description", ""),
                        "emotion": rule.get("emotion", ""),
                        "state_features": rule.get("state_features", "")
                    })
            
            if phone_action_patterns:
                # 创建或更新电话场景配置
                if "scene_types" not in self._config:
                    self._config["scene_types"] = {}
                
                self._config["scene_types"]["phone"] = {
                    "identifiers": ["电话", "手机", "接听", "来电", "通话", "拨号"],
                    "action_patterns": phone_action_patterns,
                    "action_order_weights": {},
                    "default_actions": [],
                    "dialogue_processing": {
                        "dialogue_templates": {
                            "character_dialogue": "{character}：'{dialogue}'"
                        },
                        "emotion_patterns": []
                    }
                }
        
        # 加载场景类型配置 (兼容原有逻辑)
        if "scene_types" in config_data:
            self.scene_types = {}
            for scene_type, scene_config in config_data["scene_types"].items():
                # 合并默认配置和用户配置
                default_config = self.DEFAULT_SCENE_TYPES.get(scene_type, {})
                merged_config = default_config.copy()
                merged_config.update(scene_config)
                
                # 确保所有必要字段存在
                for key in ["action_patterns", "action_order_weights", "default_actions"]:
                    if key not in merged_config:
                        merged_config[key] = default_config.get(key, [] if key != "action_order_weights" else {})
                
                # 确保对话处理配置存在
                if "dialogue_processing" not in merged_config:
                    merged_config["dialogue_processing"] = {
                        "dialogue_templates": {
                            "character_dialogue": "{character}：'{dialogue}'"
                        },
                        "emotion_patterns": []
                    }
                
                self.scene_types[scene_type] = merged_config
        
        # 加载其他直接配置项
        for key in ["scene_patterns", "dialogue_patterns", "action_emotion_map", 
                   "time_keywords", "appearance_keywords", "location_keywords", 
                   "emotion_keywords", "atmosphere_keywords"]:
            if key in config_data:
                self._config[key] = config_data[key]
        
        # 初始化所有默认配置项
        self.initialize_default_configs()
    
    def get_scene_type(self, text: str) -> Optional[str]:
        """根据文本内容识别场景类型
        
        Args:
            text: 剧本文本
            
        Returns:
            识别出的场景类型，如果未识别出则返回None
        """
        for scene_type, config in self.scene_types.items():
            identifiers = config.get("identifiers", [])
            if any(identifier in text for identifier in identifiers):
                return scene_type
        return None
    
    def get_scene_config(self, scene_type: str) -> Dict[str, Any]:
        """
        获取特定场景类型的配置
        
        Args:
            scene_type: 场景类型名称
            
        Returns:
            场景配置字典
        """
        return self.scene_types.get(scene_type, {})
        
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持从主配置中获取通用配置项
        
        Args:
            key: 配置项键名
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        return self._config.get(key, default)
        
    def initialize_default_configs(self):
        """
        初始化默认配置，确保所有必要的通用配置项都有合理的默认值
        """
        # 设置默认位置和时间
        if 'default_location' not in self._config:
            self._config['default_location'] = '室内'
        
        if 'default_time' not in self._config:
            self._config['default_time'] = '白天'
        
        # 设置默认服装关键词映射
        if 'clothing_keyword_mappings' not in self._config:
            self._config['clothing_keyword_mappings'] = {
                '毛衣': '穿着毛衣',
                '外套': '穿着外套',
                '睡衣': '穿着睡衣'
            }
        
        # 从统一关键词配置中获取状态关键词
        from penshot.neopen.config.keyword_config import get_keyword_config
        keyword_config = get_keyword_config()
        
        # 设置默认状态特征映射
        if 'state_keyword_mappings' not in self._config:
            self._config['state_keyword_mappings'] = keyword_config.get_state_keywords()
        
        # 设置默认情绪关键词（从统一配置获取）
        if 'emotion_keywords' not in self._config:
            emotion_config = keyword_config.get_emotion_keywords()
            # 转换统一配置的格式为剧本解析器需要的格式
            self._config['emotion_keywords'] = {
                '高兴': emotion_config.get('正面', []),
                '悲伤': emotion_config.get('负面', []),
                '愤怒': emotion_config.get('愤怒', []),
                '惊讶': emotion_config.get('惊讶', []),
                '恐惧': emotion_config.get('恐惧', []),
                '平静': emotion_config.get('中性', []),
                '紧张': emotion_config.get('紧张', []),
                '疑问': ['为什么', '什么', '哪里', '谁', '怎么', '如何', '是不是', '有没有']  # 特定疑问词保留
            }
        
        # 设置默认时间关键词（从统一配置获取）
        if 'time_keywords' not in self._config:
            scene_config = keyword_config.get_scene_keywords()
            self._config['time_keywords'] = {
                time: time for time in scene_config.get('时间', [])
            }
        
        # 设置默认地点关键词（从统一配置获取）
        if 'location_keywords' not in self._config:
            scene_config = keyword_config.get_scene_keywords()
            self._config['location_keywords'] = {
                loc: loc for loc in scene_config.get('室内', []) + scene_config.get('室外', []) + scene_config.get('公共空间', [])
            }
    
    def load_yaml_config(self, config_filename: str = 'script_parser_config.yaml') -> Dict[str, Any]:
        """加载YAML配置文件的公共方法
        
        Args:
            config_filename: 配置文件名
            
        Returns:
            配置数据字典，如果加载失败则返回空字典
        """
        try:
            # 根据语言选择配置文件路径
            if self._language == ShotLanguage.EN:
                # 英文配置文件放在en子目录下
                config_path = os.path.join(os.path.dirname(__file__), 'en', config_filename)
            else:
                # 中文配置文件放在zh子目录下
                config_path = os.path.join(os.path.dirname(__file__), 'zh', config_filename)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                    if config_data and isinstance(config_data, dict):
                        debug(f"成功加载配置文件: {config_path}")
                        return config_data
                    debug(f"配置文件格式不正确或为空: {config_path}")
            else:
                debug(f"配置文件不存在: {config_path}")
        except Exception as e:
            error(f"加载配置文件时出错: {str(e)}")
        
        return {}
    

    
    # 默认场景模式
    DEFAULT_SCENE_PATTERNS = [
        '场景[:：]\s*([^，。；\n]+)[，。；]\s*([^，。；\n]+)',
        '地点[:：]\s*([^，。；\n]+)[，。；]\s*时间[:：]\s*([^，。；\n]+)',
        '([^，。；\n]+)[，。；]\s*([^，。；\n]+)\s*[的]?场景',
    ]
    
    # 对话模式
    DEFAULT_DIALOGUE_PATTERNS = [
        '([^：]+)[:：]\s*(.+)',
        '([^（）]+)[（(]([^)）]+)[)）][:：]\s*(.+)',
    ]
    
    # 动作情绪映射
    DEFAULT_ACTION_EMOTION_MAP = {
        "走": "平静", "行走": "平静", "漫步": "轻松", "散步": "悠闲",
        "笑": "开心", "微笑": "愉悦", "哭": "悲伤", "流泪": "伤心",
        "颤抖": "恐惧", "紧张": "紧张", "冷静": "平静", "思考": "专注",
    }
    
    # 时间关键词映射
    DEFAULT_TIME_KEYWORDS = {
        "早上": "早晨", "早晨": "早晨", "上午": "上午", "中午": "中午",
        "下午": "下午", "晚上": "晚上", "深夜": "深夜", "凌晨": "凌晨",
    }
    
    # 外貌关键词
    DEFAULT_APPEARANCE_KEYWORDS = {
        "西装": "穿着正式西装", "休闲装": "穿着休闲服装", "老人": "年长的",
        "年轻人": "年轻的", "男人": "男性", "女人": "女性",
    }
    
    # 地点关键词
    DEFAULT_LOCATION_KEYWORDS = {
        "咖啡馆": "咖啡馆", "餐厅": "餐厅", "办公室": "办公室",
        "家": "家", "公园": "公园", "街道": "街道",
        "超市": "超市", "商场": "商场", "学校": "学校", 
        "医院": "医院", "车站": "车站", "机场": "机场",
        "酒吧": "酒吧", "电影院": "电影院", "健身房": "健身房", 
        "图书馆": "图书馆", "会议室": "会议室",
        "公寓": "公寓", "房间": "房间", "卧室": "卧室", 
        "客厅": "客厅", "厨房": "厨房", "浴室": "浴室"
    }
    
    # 情绪关键词
    DEFAULT_EMOTION_KEYWORDS = {
        "高兴": ["开心", "高兴", "快乐", "愉快", "欢乐", "兴奋", "太好了", "真棒", "哈哈"],
        "悲伤": ["伤心", "难过", "悲伤", "难过", "哭", "流泪", "痛苦", "可怜", "惨"],
        "愤怒": ["生气", "愤怒", "恼火", "气死了", "混蛋", "该死", "讨厌", "烦"],
        "惊讶": ["啊", "哇", "惊讶", "震惊", "没想到", "真的吗", "什么", "怎么会"],
        "恐惧": ["害怕", "恐惧", "恐怖", "吓死了", "救命", "不要", "危险"],
        "紧张": ["紧张", "忐忑", "不安", "焦虑", "担心", "怎么办", "不会吧"],
        "平静": ["好的", "嗯", "是的", "知道了", "明白", "了解", "好"],
        "疑问": ["为什么", "什么", "哪里", "谁", "怎么", "如何", "是不是", "有没有"]
    }
    
    # 氛围关键词
    DEFAULT_ATMOSPHERE_KEYWORDS = {
        "温馨": ["温暖", "舒适", "柔和", "愉悦", "快乐", "放松"],
        "正式": ["严肃", "庄重", "严谨", "认真"],
        "轻松": ["愉悦", "轻松", "休闲", "自在"],
        "紧张": ["紧张", "焦虑", "不安", "担忧"],
        "浪漫": ["浪漫", "甜蜜", "温馨", "幸福"],
        "悲伤": ["难过", "伤心", "悲伤", "痛苦"],
        "愤怒": ["生气", "愤怒", "恼火", "激动"],
        "惊讶": ["惊讶", "震惊", "意外", "突然"]
    }
    
    # 通用场景类型配置
    DEFAULT_SCENE_TYPES = {
        "phone": {
            "identifiers": ["电话", "手机", "接听", "来电", "通话", "拨号"],
            "action_patterns": [
                {"pattern": "(?:裹着|披着).*?靠在沙发上", "description": "{0}靠在沙发上", "emotion": "平静", "state_features": "身体放松，靠在沙发backed，目光柔和"},
                {"pattern": "手机震动|手机.*?震动|震动", "description": "手机震动", "emotion": "警觉", "state_features": "目光转向手机，身体微微前倾，手指轻触沙发扶手"},
                {"pattern": "犹豫.*?拿起手机", "description": "犹豫着伸手拿起手机", "emotion": "犹豫+警觉", "state_features": "下唇轻咬，手指无意识地摩挲手机边缘，目光闪烁不定"},
                {"pattern": "查看屏幕|看手机屏幕", "description": "低头查看屏幕", "emotion": "犹豫+警觉", "state_features": "手指微微颤抖，目光在手机和周围环境间游移"},
                {"pattern": "按下接听键|接起电话|接听电话", "description": "接起电话，将手机贴在耳边", "emotion": "警觉", "state_features": "手指微微颤抖，耳朵贴近手机，呼吸变得轻缓"},
                {"pattern": "轻声问.*?|.*?轻声说", "description": "轻声问：'{1}'", "emotion": "试探+紧张", "state_features": "手指收紧，声音轻微颤抖，身体微微前倾"},
                {"pattern": "对方.*?说|对方表示", "description": "听到对方说：'{1}'", "emotion": "震惊", "state_features": "瞳孔骤缩，指节泛白，肩膀微微抖动"},
                {"pattern": "电话那头传来[^：:]*[：:][\'\"](.+?)[\'\"]", "description": "听到电话中传来：'\1'", "emotion": "震惊", "state_features": "身体瞬间僵直，手指关节因握力过猛而泛白，呼吸凝滞"},
                {"pattern": "传来[^：:]*[：:][\'\"](.+?)[\'\"]", "description": "听到传来的声音：'\1'", "emotion": "震惊", "state_features": "身体瞬间僵直，手指关节因握力过猛而泛白，呼吸凝滞"},
                {"pattern": "听到对方[^：:]*[：:][\'\"](.+?)[\'\"]|对方[^：:]*[：:][\'\"](.+?)[\'\"]", "description": "听到对方说：'{1}'", "emotion": "震惊", "state_features": "瞳孔骤然收缩，呼吸急促，手指紧紧攥住手机边缘"},
                {"pattern": "攥紧手机|指节发白|猛地一颤|猛然僵直|震惊", "description": "身体猛然僵直", "emotion": "崩溃", "state_features": "瞳孔骤缩，指节泛白，肩膀剧烈抖动"},
                {"pattern": "滑落|脱手|掉落", "description": "肩膀剧烈抖动，手中物品滑落", "emotion": "崩溃", "state_features": "双手本能撑住附近物体，指节因用力而泛白"},
            ],
            "action_order_weights": {
                "手机震动": 1,
                "犹豫着伸手拿起手机": 2,
                "低头查看屏幕": 3,
                "接起电话，将手机贴在耳边": 4,
                "轻声问.*?": 5,
                "听到对方说.*?": 6,
                "身体猛然僵直": 7,
                "肩膀剧烈抖动，手中物品滑落": 8,
            },
            "default_actions": [
                {"priority": 50, "description": "身体微微颤抖，表情变得紧张", "emotion": "紧张", "state_features": "手指微微颤抖，呼吸变得急促"},
                {"priority": 100, "description": "对方挂断电话，留下一片寂静", "emotion": "失落", "state_features": "目光呆滞，手机慢慢从耳边移开"},
            ],
            "dialogue_processing": {
                "dialogue_templates": {
                    "character_dialogue": "{character}：'{dialogue}'",
                    "phone_dialogue": "听到电话中传来：'{dialogue}'"
                },
                "emotion_patterns": [
                    {"pattern": "我回来了|回来|到家", "emotion": "震惊+感动"},
                    {"pattern": "分手|结束|离开", "emotion": "悲伤+崩溃"},
                    {"pattern": "是我|我是", "emotion": "惊讶+疑惑"},
                    {"pattern": "？|？$|？\\n", "emotion": "疑惑+紧张"},
                ]
            }
        },
        "meeting": {
            "identifiers": ["会议", "讨论", "商谈", "谈判", "汇报"],
            "action_patterns": [
                {"pattern": "走进会议室|进入会议室", "description": "走进会议室，环顾四周", "emotion": "平静+专注", "state_features": "步伐沉稳，目光扫视会议室，双手自然下垂"},
                {"pattern": "坐下|就座", "description": "在会议桌前坐下", "emotion": "专注", "state_features": "背部挺直，双手放在桌上，目光正视前方"},
            ],
            "action_order_weights": {
                "走进会议室，环顾四周": 1,
                "在会议桌前坐下": 2,
            },
            "default_actions": [
                {"priority": 50, "description": "认真聆听对方发言", "emotion": "专注", "state_features": "身体微微前倾，目光专注，偶尔点头"},
            ],
            "dialogue_processing": {
                "dialogue_templates": {
                    "character_dialogue": "{character}：'{dialogue}'",
                    "meeting_dialogue": "{character}在会议中说：'{dialogue}'"
                }
            }
        }
    }

    
    # 地点正则模式
    @staticmethod
    def get_location_patterns() -> List[re.Pattern]:
        """获取地点识别的正则模式"""
        return [
            re.compile(r'在([^，。；\n]+)[处里内]'),
            re.compile(r'位于([^，。；\n]+)'),
            re.compile(r'来到([^，。；\n]+)'),
            re.compile(r'走进([^，。；\n]+)'),
            re.compile(r'([^，。；\n]+)[内]'),  # 匹配"公寓内"这种格式
        ]
    
    @staticmethod
    def extract_time(time_hint: str) -> str:
        """从时间提示中提取标准时间格式
        
        Args:
            time_hint: 包含时间信息的文本
            
        Returns:
            格式化后的时间字符串
        """
        # 首先检查是否包含深夜/凌晨关键词
        if any(keyword in time_hint for keyword in ['深夜', '凌晨', '夜晚']):
            # 检查是否包含具体时间
            time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', time_hint)
            if time_match:
                hour = int(time_match.group(1))
                minute = time_match.group(2)
                # 深夜时间保持原样，不转换为12小时制
                return f"深夜{hour}:{minute}"
            
            # 检查是否包含数字+时间单位
            hour_match = re.search(r'(\d{1,2})[点时]', time_hint)
            if hour_match:
                hour = int(hour_match.group(1))
                return f"深夜{hour}点"
            return "深夜"

        # 检查是否包含具体时间
        time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', time_hint)
        if time_match:
            hour = int(time_match.group(1))
            minute = time_match.group(2)
            # 根据时间判断时段
            if hour < 6:
                period = "凌晨"
            elif hour < 12:
                period = "上午"
            elif hour < 18:
                period = "下午"
            else:
                period = "晚上"
            
            # 对于非凌晨/深夜时间，转换为12小时制
            if period not in ['凌晨', '深夜'] and hour > 12:
                hour = hour - 12
            
            return f"{period}{hour}:{minute}"

        # 检查是否包含时段关键词
        for keyword, time_period in ScriptParserConfig.DEFAULT_TIME_KEYWORDS.items():
            if keyword in time_hint:
                return time_period

        # 检查是否包含数字+时间单位
        hour_match = re.search(r'(\d{1,2})[点时]', time_hint)
        if hour_match:
            hour = int(hour_match.group(1))
            # 根据时间判断时段
            if hour < 6:
                period = "凌晨"
            elif hour < 12:
                period = "上午"
            elif hour < 18:
                period = "下午"
            else:
                period = "晚上"
            
            # 对于非凌晨/深夜时间，转换为12小时制
            if period not in ['凌晨', '深夜'] and hour > 12:
                hour = hour - 12
            
            return f"{period}{hour}点"

        return "下午3点"  # 默认时间
    
    @staticmethod
    def extract_time_from_text(text: str) -> Optional[str]:
        """从文本中提取时间信息
        
        Args:
            text: 包含时间信息的文本
            
        Returns:
            提取的时间字符串，如果未提取到则返回None
        """
        # 首先检查是否包含深夜/凌晨关键词
        if any(keyword in text for keyword in ['深夜', '凌晨', '夜晚']):
            # 尝试提取具体时间
            time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', text)
            if time_match:
                hour = int(time_match.group(1))
                minute = time_match.group(2)
                return f"深夜{hour}:{minute}"
            
            # 检查是否包含数字+时间单位
            hour_match = re.search(r'(\d{1,2})[点时]', text)
            if hour_match:
                hour = int(hour_match.group(1))
                return f"深夜{hour}点"
            return "深夜"

        # 检查时间段关键词
        for keyword, time_period in ScriptParserConfig.DEFAULT_TIME_KEYWORDS.items():
            if keyword in text:
                # 尝试提取具体时间
                time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', text)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = time_match.group(2)
                    # 根据时间判断时段
                    if hour < 6:
                        period = "凌晨"
                    elif hour < 12:
                        period = "上午"
                    elif hour < 18:
                        period = "下午"
                    else:
                        period = "晚上"
                    
                    # 对于非凌晨/深夜时间，转换为12小时制
                    if period not in ['凌晨', '深夜'] and hour > 12:
                        hour = hour - 12
                    
                    return f"{period}{hour}:{minute}"
                return time_period

        # 检查是否有具体时间
        time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = time_match.group(2)
            # 根据时间判断时段
            if hour < 6:
                period = "凌晨"
            elif hour < 12:
                period = "上午"
            elif hour < 18:
                period = "下午"
            else:
                period = "晚上"
            
            # 对于非凌晨/深夜时间，转换为12小时制
            if period not in ['凌晨', '深夜'] and hour > 12:
                hour = hour - 12
            
            return f"{period}{hour}:{minute}"
        
        return None
    
    @staticmethod
    def initialize_patterns(config_path: Optional[str] = None) -> Dict[str, Any]:
        """初始化中文剧本解析需要的模式和关键词
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            包含所有解析模式和关键词的字典
        """
        # 获取全局配置实例
        temp_instance = script_parser_config
        
        # 默认配置
        default_config = {
            "scene_patterns": temp_instance.DEFAULT_SCENE_PATTERNS,
            "dialogue_patterns": temp_instance.DEFAULT_DIALOGUE_PATTERNS,
            "action_emotion_map": temp_instance.DEFAULT_ACTION_EMOTION_MAP,
            "time_keywords": temp_instance.DEFAULT_TIME_KEYWORDS,
            "appearance_keywords": temp_instance.DEFAULT_APPEARANCE_KEYWORDS,
            "location_keywords": temp_instance.DEFAULT_LOCATION_KEYWORDS,
            "emotion_keywords": temp_instance.DEFAULT_EMOTION_KEYWORDS,
            "atmosphere_keywords": temp_instance.DEFAULT_ATMOSPHERE_KEYWORDS,
            "scene_types": temp_instance.DEFAULT_SCENE_TYPES
        }

        # 尝试从配置文件加载
        config_data = default_config.copy()
        try:
            # 首先尝试加载YAML配置
            if config_path:
                import os
                config_filename = os.path.basename(config_path)
                loaded_config = temp_instance.load_yaml_config(config_filename)
            else:
                loaded_config = temp_instance._get_cached_config()
            
            # 重要：将加载的配置应用到实例中
            if loaded_config and isinstance(loaded_config, dict):
                temp_instance.load_config(loaded_config)
                
            # 确保loaded_config不为None
            if loaded_config is not None and isinstance(loaded_config, dict):
                # 支持新的配置结构（嵌套结构）
                if "parse_rules" in loaded_config:
                    parse_rules = loaded_config["parse_rules"]
                    
                    # 提取场景识别规则
                    if "scene_recognition" in parse_rules:
                        scene_recog = parse_rules["scene_recognition"]
                        # 合并场景相关的模式
                        all_scene_patterns = []
                        if "start_patterns" in scene_recog:
                            all_scene_patterns.extend(scene_recog["start_patterns"])
                        if "transition_patterns" in scene_recog:
                            all_scene_patterns.extend(scene_recog["transition_patterns"])
                        if "end_patterns" in scene_recog:
                            all_scene_patterns.extend(scene_recog["end_patterns"])
                        if all_scene_patterns:
                            config_data["scene_patterns"] = all_scene_patterns
                    
                    # 提取角色识别规则
                    if "character_recognition" in parse_rules:
                        char_recog = parse_rules["character_recognition"]
                        if "name_patterns" in char_recog:
                            # 将角色名提取模式作为对话模式的一部分
                            config_data["dialogue_patterns"] = char_recog["name_patterns"]
                    
                    # 提取对话识别规则
                    if "dialogue_recognition" in parse_rules:
                        dial_recog = parse_rules["dialogue_recognition"]
                        all_dialogue_patterns = []
                        if "direct_patterns" in dial_recog:
                            all_dialogue_patterns.extend(dial_recog["direct_patterns"])
                        if "indirect_patterns" in dial_recog:
                            all_dialogue_patterns.extend(dial_recog["indirect_patterns"])
                        if all_dialogue_patterns:
                            # 如果有角色名模式和对话模式，合并它们
                            if "dialogue_patterns" in config_data:
                                config_data["dialogue_patterns"].extend(all_dialogue_patterns)
                            else:
                                config_data["dialogue_patterns"] = all_dialogue_patterns
                    
                    # 提取情绪识别规则
                    if "emotion_recognition" in parse_rules and "keywords" in parse_rules["emotion_recognition"]:
                        emotion_keywords = parse_rules["emotion_recognition"]["keywords"]
                        # 转换为旧格式的情绪关键词映射
                        emotion_map = {}
                        for emotion_type, words in emotion_keywords.items():
                            if isinstance(words, list):
                                emotion_map[emotion_type] = words
                        if emotion_map:
                            config_data["emotion_keywords"] = emotion_map
                
                # 处理场景特殊规则（从新配置中提取电话场景相关配置）
                phone_scenario_action_patterns = []
                if "scene_special_rules" in loaded_config:
                    for rule in loaded_config["scene_special_rules"]:
                        if "pattern" in rule and isinstance(rule, dict):
                            # 转换为手机场景动作模式格式
                            phone_scenario_action_patterns.append({
                                "pattern": rule["pattern"],
                                "description": rule.get("description", ""),
                                "emotion": rule.get("emotion", ""),
                                "state_features": rule.get("state_features", "")
                            })
                
                if phone_scenario_action_patterns:
                    config_data["phone_scenario_action_patterns"] = phone_scenario_action_patterns
                    
                    # 为手机场景创建默认的scene_types配置
                    if "scene_types" not in config_data:
                        config_data["scene_types"] = {}
                    config_data["scene_types"]["phone"] = {
                        "identifiers": ["电话", "手机", "接听", "来电", "通话", "拨号"],
                        "action_patterns": phone_scenario_action_patterns,
                        "action_order_weights": {},
                        "default_actions": [],
                        "dialogue_processing": {
                            "dialogue_templates": {
                                "character_dialogue": "{character}：'{dialogue}'"
                            },
                            "emotion_patterns": []
                        }
                    }
                
                # 保留对旧配置结构的支持（向后兼容）
                for key in ["scene_patterns", "dialogue_patterns", "action_emotion_map", 
                           "time_keywords", "appearance_keywords", "location_keywords", 
                           "emotion_keywords", "atmosphere_keywords", "scene_types"]:
                    if key in loaded_config:
                        config_data[key] = loaded_config[key]
                
                # 特殊处理scene_types配置，并转换为phone_scenario相关配置
                if "scene_types" in loaded_config and isinstance(loaded_config["scene_types"], dict):
                    config_data["scene_types"] = loaded_config["scene_types"]
                    
                    # 从scene_types中提取phone场景配置
                    if "phone" in loaded_config["scene_types"]:
                        phone_config = loaded_config["scene_types"]["phone"]
                        
                        # 更新手机场景相关配置
                        if "action_patterns" in phone_config:
                            config_data["phone_scenario_action_patterns"] = phone_config["action_patterns"]
                        if "action_order_weights" in phone_config:
                            config_data["phone_scenario_action_order_weights"] = phone_config["action_order_weights"]
                        if "default_actions" in phone_config:
                            config_data["phone_scenario_default_actions"] = phone_config["default_actions"]
                        
                        # 从dialogue_processing中提取必要对话配置
                        if "dialogue_processing" in phone_config and "emotion_patterns" in phone_config["dialogue_processing"]:
                            # 转换为旧格式的必要对话
                            required_dialogues = []
                            for pattern in phone_config["dialogue_processing"]["emotion_patterns"]:
                                if isinstance(pattern, dict):
                                    pattern_text = pattern.get("pattern", "")
                                    emotion = pattern.get("emotion", "")
                                    
                                    # 提取示例文本
                                    if "我回来了" in pattern_text:
                                        required_dialogues.append({"text": "我回来了", "action_template": "听到对方低声说：'{text}'", "emotion": emotion})
                                    elif "是我" in pattern_text:
                                        required_dialogues.append({"text": "是我", "action_template": "听到电话中传来沙哑男声：'{text}'", "emotion": emotion})
                            
                            if required_dialogues:
                                config_data["phone_scenario_required_dialogues"] = required_dialogues
                
                debug(f"成功从配置文件加载剧本解析配置")
                # 打印配置信息，用于调试
                # print(f"配置加载成功: ")
                # print(f"  - 场景识别模式: {len(config_data.get('scene_patterns', []))} 个")
                # print(f"  - 对话识别模式: {len(config_data.get('dialogue_patterns', []))} 个")
                # print(f"  - 动作情绪映射: {len(config_data.get('action_emotion_map', {}))} 个")
                # print(f"  - 角色外观关键词: {len(config_data.get('appearance_keywords', {}))} 个")
                # print(f"  - 时段关键词: {len(config_data.get('time_keywords', {}))} 个")
                # print(f"  - 地点关键词: {len(config_data.get('location_keywords', {}))} 个")
                # print(f"  - 情绪关键词: {len(config_data.get('emotion_keywords', {}))} 个")
                # print(f"  - 场景氛围关键词: {len(config_data.get('atmosphere_keywords', {}))} 个")
                # print(f"  - 手机场景动作模式: {len(config_data.get('phone_scenario_action_patterns', []))} 个")
                # print(f"  - 手机场景动作顺序权重: {len(config_data.get('phone_scenario_action_order_weights', {}))} 个")
                # print(f"  - 场景类型配置: {len(config_data.get('scene_types', {}))} 个")
        except Exception as e:
            warning(f"无法加载配置文件，使用默认配置: {str(e)}")

        # 编译正则表达式模式
        scene_patterns = []
        for pattern_str in config_data.get('scene_patterns', []):
            try:
                # 注意：这里需要添加r前缀以确保正则表达式中的转义字符正确处理
                scene_patterns.append(re.compile(pattern_str))
            except re.error as e:
                warning(f"正则表达式模式编译失败: {pattern_str}, 错误: {str(e)}")

        # 编译对话模式
        dialogue_patterns = []
        for pattern_str in config_data.get('dialogue_patterns', []):
            try:
                dialogue_patterns.append(re.compile(pattern_str))
            except re.error as e:
                warning(f"对话模式编译失败: {pattern_str}, 错误: {str(e)}")

        # 如果对话模式为空，使用默认模式
        if not dialogue_patterns:
            dialogue_patterns = [
                re.compile(r'([^：]+)[:：]\s*(.+)'),
                re.compile(r'([^（）]+)[（(]([^)）]+)[)）][:：]\s*(.+)')
            ]


        return {
            "scene_patterns": scene_patterns,
            "dialogue_patterns": dialogue_patterns,
            "action_emotion_map": config_data.get('action_emotion_map', {}),
            "time_keywords": config_data.get('time_keywords', {}),
            "appearance_keywords": config_data.get('appearance_keywords', {}),
            "location_keywords": config_data.get('location_keywords', {}),
            "emotion_keywords": config_data.get('emotion_keywords', {}),
            "atmosphere_keywords": config_data.get('atmosphere_keywords', {}),
            "phone_scenario_action_order_weights": config_data.get('phone_scenario_action_order_weights', {}),
            "phone_scenario_default_actions": config_data.get('phone_scenario_default_actions', []),
            "phone_scenario_required_dialogues": config_data.get('phone_scenario_required_dialogues', [])
        }
    
    @staticmethod
    def extract_location_from_text(text: str, location_keywords: Optional[Dict[str, str]] = None) -> Optional[str]:
        """从文本中提取地点信息
        
        Args:
            text: 包含地点信息的文本
            location_keywords: 自定义地点关键词字典
            
        Returns:
            提取的地点字符串，如果未提取到则返回None
        """
        # 获取地点正则模式
        location_patterns = ScriptParserConfig.get_location_patterns()

        # 使用从配置加载的地点关键词
        common_locations = list(location_keywords.keys()) if location_keywords else ScriptParserConfig.DEFAULT_LOCATION_KEYWORDS.keys()

        # 首先尝试模式匹配
        for pattern in location_patterns:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()

        # 然后检查常见地点关键词
        for location in common_locations:
            if location in text:
                # 尝试提取更具体的地点描述
                location_match = re.search(f'(.{{0,20}}){location}(.{{0,10}})', text)
                if location_match:
                    full_location = location_match.group(0).strip()
                    # 清理多余字符
                    full_location = re.sub(r'[，。；：]', '', full_location)
                    return full_location
                return location

        return None


# 创建配置实例供外部使用
script_parser_config = ScriptParserConfig()