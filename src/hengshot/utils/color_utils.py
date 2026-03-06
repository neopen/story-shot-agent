"""
@FileName: color_utils.py
@Description: 色彩处理工具
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/6 15:12
"""
import colorsys
import re
from typing import List, Tuple, Dict, Any


class ColorUtils:
    """色彩处理工具类"""

    # 标准颜色名称到十六进制的映射
    COLOR_NAME_TO_HEX = {
        # 基础色
        "red": "#FF0000",
        "green": "#00FF00",
        "blue": "#0000FF",
        "yellow": "#FFFF00",
        "cyan": "#00FFFF",
        "magenta": "#FF00FF",
        "white": "#FFFFFF",
        "black": "#000000",
        "gray": "#808080",

        # 暖色系
        "warm_red": "#FF6B6B",
        "orange": "#FFA500",
        "gold": "#FFD700",
        "amber": "#FFBF00",
        "coral": "#FF7F50",
        "salmon": "#FA8072",
        "peach": "#FFE5B4",
        "beige": "#F5F5DC",

        # 冷色系
        "cool_blue": "#4169E1",
        "teal": "#008080",
        "turquoise": "#40E0D0",
        "mint": "#98FF98",
        "lavender": "#E6E6FA",
        "lilac": "#C8A2C8",
        "ice_blue": "#F0FFFF",

        # 中性色
        "charcoal": "#36454F",
        "slate": "#708090",
        "taupe": "#483C32",
        "khaki": "#F0E68C",
        "cream": "#FFFDD0",

        # 电影常用色
        "cinematic_blue": "#0A2342",
        "cinematic_teal": "#008B8B",
        "cinematic_orange": "#FF8C00",
        "cinematic_gold": "#D4AF37",
        "cinematic_silver": "#C0C0C0",
        "cinematic_dark": "#1A1A1A",
    }

    # 情绪到色彩调色板的映射
    EMOTION_COLOR_PALETTES = {
        "happy": {
            "dominant": ["#FFD700", "#FF6B6B", "#98FF98"],  # 金色、暖红、薄荷绿
            "mood": "bright and vibrant",
            "temperature": "warm"
        },
        "sad": {
            "dominant": ["#708090", "#696969", "#5F9EA0"],  # 石板灰、暗灰、卡其灰
            "mood": "muted and desaturated",
            "temperature": "cool"
        },
        "romantic": {
            "dominant": ["#FFB6C1", "#E6E6FA", "#FF69B4"],  # 浅粉、薰衣草、深粉
            "mood": "soft and dreamy",
            "temperature": "warm"
        },
        "tense": {
            "dominant": ["#8B0000", "#2F4F4F", "#4B0082"],  # 深红、深灰绿、靛青
            "mood": "dark and high contrast",
            "temperature": "cool"
        },
        "mysterious": {
            "dominant": ["#4B0082", "#191970", "#2E8B57"],  # 靛青、午夜蓝、海绿
            "mood": "deep and enigmatic",
            "temperature": "cool"
        },
        "epic": {
            "dominant": ["#D4AF37", "#0A2342", "#8B0000"],  # 金色、深蓝、深红
            "mood": "rich and dramatic",
            "temperature": "mixed"
        },
        "natural": {
            "dominant": ["#228B22", "#8B4513", "#F4A460"],  # 森林绿、马鞍棕、沙棕
            "mood": "organic and earthy",
            "temperature": "neutral"
        },
        "neutral": {
            "dominant": ["#808080", "#C0C0C0", "#D3D3D3"],  # 中灰、银色、浅灰
            "mood": "balanced and calm",
            "temperature": "neutral"
        }
    }

    # 时间到色彩的映射
    TIME_OF_DAY_COLORS = {
        "morning": {
            "light_color": "#FFD700",  # 金色阳光
            "shadow_color": "#87CEEB",  # 天蓝色
            "temperature": "warm",
            "contrast": "medium"
        },
        "afternoon": {
            "light_color": "#FF8C00",  # 深橙色
            "shadow_color": "#4682B4",  # 钢蓝色
            "temperature": "warm",
            "contrast": "high"
        },
        "golden_hour": {
            "light_color": "#FF4500",  # 橙红色
            "shadow_color": "#4B0082",  # 靛青色
            "temperature": "very warm",
            "contrast": "very high"
        },
        "evening": {
            "light_color": "#FF6347",  # 番茄红
            "shadow_color": "#191970",  # 午夜蓝
            "temperature": "warm",
            "contrast": "medium"
        },
        "night": {
            "light_color": "#4169E1",  # 皇家蓝
            "shadow_color": "#000080",  # 海军蓝
            "temperature": "cool",
            "contrast": "low"
        },
        "midnight": {
            "light_color": "#4B0082",  # 靛青
            "shadow_color": "#000000",  # 纯黑
            "temperature": "very cool",
            "contrast": "very low"
        }
    }

    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        """十六进制颜色转RGB"""
        hex_color = hex_color.lstrip('#')

        if len(hex_color) == 3:
            # 扩展缩写格式 #RGB -> #RRGGBB
            hex_color = ''.join([c * 2 for c in hex_color])
        elif len(hex_color) != 6:
            raise ValueError(f"Invalid hex color: {hex_color}")

        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16)
        )

    @staticmethod
    def rgb_to_hex(r: int, g: int, b: int) -> str:
        """RGB转十六进制颜色"""
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
        """RGB转HSL"""
        r_norm = r / 255.0
        g_norm = g / 255.0
        b_norm = b / 255.0

        h, l, s = colorsys.rgb_to_hls(r_norm, g_norm, b_norm)
        return (h, s, l)

    @staticmethod
    def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
        """HSL转RGB"""
        r_norm, g_norm, b_norm = colorsys.hls_to_rgb(h, l, s)
        return (
            int(r_norm * 255),
            int(g_norm * 255),
            int(b_norm * 255)
        )

    @staticmethod
    def calculate_color_distance(color1: str, color2: str) -> float:
        """计算两个颜色的欧几里得距离（在RGB空间）"""
        rgb1 = ColorUtils.hex_to_rgb(color1)
        rgb2 = ColorUtils.hex_to_rgb(color2)

        distance = sum((c1 - c2) ** 2 for c1, c2 in zip(rgb1, rgb2)) ** 0.5
        return distance

    @staticmethod
    def calculate_hue_distance(color1: str, color2: str) -> float:
        """计算两个颜色的色调距离"""
        rgb1 = ColorUtils.hex_to_rgb(color1)
        rgb2 = ColorUtils.hex_to_rgb(color2)

        h1, _, _ = ColorUtils.rgb_to_hsl(*rgb1)
        h2, _, _ = ColorUtils.rgb_to_hsl(*rgb2)

        # 色调在0-1之间，计算最短距离
        diff = abs(h1 - h2)
        return min(diff, 1 - diff)

    @staticmethod
    def get_color_temperature(hex_color: str) -> str:
        """判断颜色温度（暖色/冷色/中性）"""
        rgb = ColorUtils.hex_to_rgb(hex_color)
        h, s, l = ColorUtils.rgb_to_hsl(*rgb)

        # 基于色调判断冷暖
        # 暖色：红色到黄色 (0-60度或300-360度)
        # 冷色：青色到蓝色 (180-240度)
        hue_degrees = h * 360

        if (hue_degrees >= 0 and hue_degrees <= 60) or (hue_degrees >= 300 and hue_degrees <= 360):
            return "warm"
        elif hue_degrees >= 180 and hue_degrees <= 240:
            return "cool"
        else:
            return "neutral"

    @staticmethod
    def adjust_color_temperature(hex_color: str, target_temperature: str, strength: float = 0.5) -> str:
        """调整颜色温度"""
        rgb = ColorUtils.hex_to_rgb(hex_color)
        h, s, l = ColorUtils.rgb_to_hsl(*rgb)
        current_temp = ColorUtils.get_color_temperature(hex_color)

        if current_temp == target_temperature:
            return hex_color

        hue_degrees = h * 360

        if target_temperature == "warm":
            # 向暖色调调整（红色/橙色方向）
            if hue_degrees < 60:
                new_hue = (hue_degrees + 15 * strength) % 360
            elif hue_degrees > 180:
                # 从冷色区向暖色区调整
                new_hue = (hue_degrees - 60 * strength) % 360
            else:
                new_hue = 30  # 橙色
        elif target_temperature == "cool":
            # 向冷色调调整（蓝色方向）
            if hue_degrees > 180:
                new_hue = (hue_degrees + 15 * strength) % 360
            else:
                # 从暖色区向冷色区调整
                new_hue = (hue_degrees + 120 * strength) % 360
        else:  # neutral
            # 向中性色调整（绿色/紫色方向）
            if hue_degrees < 120:
                new_hue = (hue_degrees + 60 * strength) % 360
            else:
                new_hue = (hue_degrees - 60 * strength) % 360

        new_h = new_hue / 360.0
        new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)

        return ColorUtils.rgb_to_hex(*new_rgb)

    @staticmethod
    def create_color_palette(base_color: str, palette_type: str = "analogous") -> List[str]:
        """创建色彩调色板"""
        rgb = ColorUtils.hex_to_rgb(base_color)
        h, s, l = ColorUtils.rgb_to_hsl(*rgb)

        palette = []

        if palette_type == "analogous":
            # 类似色：色轮上相邻的颜色
            for i in [-0.083, 0, 0.083]:  # 大约30度
                new_h = (h + i) % 1.0
                new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)
                palette.append(ColorUtils.rgb_to_hex(*new_rgb))

        elif palette_type == "complementary":
            # 互补色：色轮上相对的颜色
            new_h = (h + 0.5) % 1.0  # 180度
            new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)
            palette.append(ColorUtils.rgb_to_hex(*new_rgb))

        elif palette_type == "triadic":
            # 三元色：色轮上等距的三个颜色
            for i in [0, 0.333, 0.667]:  # 120度间隔
                new_h = (h + i) % 1.0
                new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)
                palette.append(ColorUtils.rgb_to_hex(*new_rgb))

        elif palette_type == "monochromatic":
            # 单色调：同一色调不同明度/饱和度
            for i in [0.7, 0.85, 1.0, 0.7, 0.4]:  # 不同饱和度
                for j in [0.3, 0.5, 0.7, 0.9]:  # 不同明度
                    new_rgb = ColorUtils.hsl_to_rgb(h, s * i, l * j)
                    palette.append(ColorUtils.rgb_to_hex(*new_rgb))

        elif palette_type == "split_complementary":
            # 分裂互补色
            for i in [0.416, 0.584]:  # 150度和210度
                new_h = (h + i) % 1.0
                new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)
                palette.append(ColorUtils.rgb_to_hex(*new_rgb))

        return list(set(palette[:5]))  # 返回最多5个颜色

    @staticmethod
    def extract_color_from_text(text: str) -> List[str]:
        """从文本中提取颜色"""
        # 中文颜色名称映射
        chinese_color_map = {
            "红色": "#FF0000", "蓝色": "#0000FF", "绿色": "#00FF00",
            "黄色": "#FFFF00", "黑色": "#000000", "白色": "#FFFFFF",
            "灰色": "#808080", "橙色": "#FFA500", "紫色": "#800080",
            "粉色": "#FFC0CB", "棕色": "#A52A2A", "青色": "#00FFFF",
            "金色": "#FFD700", "银色": "#C0C0C0", "咖啡色": "#8B4513",
            "米色": "#F5F5DC", "卡其色": "#F0E68C", "藏青色": "#000080",
        }

        found_colors = []

        # 检查中文颜色名称
        for chinese_name, hex_color in chinese_color_map.items():
            if chinese_name in text:
                found_colors.append(hex_color)

        # 检查英文颜色名称
        text_lower = text.lower()
        for english_name, hex_color in ColorUtils.COLOR_NAME_TO_HEX.items():
            if english_name in text_lower:
                found_colors.append(hex_color)

        # 检查十六进制颜色代码
        hex_pattern = r'#(?:[0-9a-fA-F]{3}){1,2}'
        hex_matches = re.findall(hex_pattern, text)
        found_colors.extend(hex_matches)

        # 检查RGB格式
        rgb_pattern = r'rgb\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})\)'
        rgb_matches = re.findall(rgb_pattern, text)
        for r, g, b in rgb_matches:
            hex_color = ColorUtils.rgb_to_hex(int(r), int(g), int(b))
            found_colors.append(hex_color)

        return list(set(found_colors))  # 去重

    @staticmethod
    def get_palette_for_emotion(emotion: str) -> Dict[str, Any]:
        """获取情绪对应的色彩调色板"""
        return ColorUtils.EMOTION_COLOR_PALETTES.get(
            emotion.lower(),
            ColorUtils.EMOTION_COLOR_PALETTES["neutral"]
        )

    @staticmethod
    def get_colors_for_time_of_day(time_of_day: str) -> Dict[str, Any]:
        """获取时间对应的色彩"""
        return ColorUtils.TIME_OF_DAY_COLORS.get(
            time_of_day.lower(),
            ColorUtils.TIME_OF_DAY_COLORS["afternoon"]  # 默认下午
        )

    @staticmethod
    def generate_cinematic_color_palette(style: str = "teal_and_orange") -> Dict[str, List[str]]:
        """生成电影感色彩调色板"""
        palettes = {
            "teal_and_orange": {
                "dominant": ["#008B8B", "#FF8C00"],  # 深青色和深橙色
                "secondary": ["#0A2342", "#F4A460", "#2F4F4F"],  # 深蓝、沙棕、深灰绿
                "accent": ["#FFD700", "#8B0000"],  # 金色、深红
                "temperature": "mixed",
                "mood": "cinematic and dramatic"
            },
            "blue_and_yellow": {
                "dominant": ["#1E90FF", "#FFD700"],  # 道奇蓝和金色
                "secondary": ["#191970", "#FFA500", "#4682B4"],  # 午夜蓝、橙色、钢蓝
                "accent": ["#FF4500", "#32CD32"],  # 橙红、酸橙绿
                "temperature": "mixed",
                "mood": "vibrant and energetic"
            },
            "monochrome_green": {
                "dominant": ["#006400", "#32CD32", "#98FB98"],  # 深绿、酸橙绿、淡绿
                "secondary": ["#8FBC8F", "#556B2F", "#ADFF2F"],  # 暗海绿、暗橄榄绿、绿黄
                "accent": ["#FFD700", "#8B4513"],  # 金色、马鞍棕
                "temperature": "neutral",
                "mood": "natural and organic"
            },
            "purple_and_pink": {
                "dominant": ["#4B0082", "#FF69B4"],  # 靛青、深粉
                "secondary": ["#9370DB", "#DA70D6", "#8A2BE2"],  # 中紫、兰紫、蓝紫
                "accent": ["#00FFFF", "#FFD700"],  # 青色、金色
                "temperature": "cool",
                "mood": "mysterious and romantic"
            },
            "sepia_vintage": {
                "dominant": ["#8B7355", "#D2B48C"],  # 土黄、黄褐
                "secondary": ["#696969", "#A0522D", "#CD853F"],  # 暗灰、土棕、秘鲁棕
                "accent": ["#8B0000", "#2F4F4F"],  # 深红、深灰绿
                "temperature": "warm",
                "mood": "nostalgic and vintage"
            }
        }

        return palettes.get(style, palettes["teal_and_orange"])

    @staticmethod
    def calculate_color_harmony_score(colors: List[str]) -> float:
        """计算颜色和谐度得分（0-1）"""
        if len(colors) < 2:
            return 1.0

        total_distance = 0
        comparisons = 0

        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                # 计算色调距离
                hue_distance = ColorUtils.calculate_hue_distance(colors[i], colors[j])

                # 和谐的距离：要么很近（类似色），要么适中（互补/三元），要么很远（分裂互补）
                if hue_distance < 0.083:  # 30度以内：类似色
                    harmony = 1.0 - (hue_distance / 0.083)
                elif abs(hue_distance - 0.5) < 0.083:  # 180度附近：互补色
                    harmony = 1.0 - (abs(hue_distance - 0.5) / 0.083)
                elif abs(hue_distance - 0.333) < 0.083:  # 120度附近：三元色
                    harmony = 1.0 - (abs(hue_distance - 0.333) / 0.083)
                else:
                    harmony = 0.5  # 不太和谐

                total_distance += harmony
                comparisons += 1

        return total_distance / comparisons if comparisons > 0 else 1.0

    @staticmethod
    def adjust_saturation(hex_color: str, factor: float) -> str:
        """调整颜色饱和度"""
        rgb = ColorUtils.hex_to_rgb(hex_color)
        h, s, l = ColorUtils.rgb_to_hsl(*rgb)

        new_s = max(0.0, min(1.0, s * factor))
        new_rgb = ColorUtils.hsl_to_rgb(h, new_s, l)

        return ColorUtils.rgb_to_hex(*new_rgb)

    @staticmethod
    def adjust_brightness(hex_color: str, factor: float) -> str:
        """调整颜色明度"""
        rgb = ColorUtils.hex_to_rgb(hex_color)
        h, s, l = ColorUtils.rgb_to_hsl(*rgb)

        new_l = max(0.0, min(1.0, l * factor))
        new_rgb = ColorUtils.hsl_to_rgb(h, s, new_l)

        return ColorUtils.rgb_to_hex(*new_rgb)

    @staticmethod
    def get_contrasting_color(hex_color: str, contrast_type: str = "text") -> str:
        """获取对比色（用于文字或背景）"""
        rgb = ColorUtils.hex_to_rgb(hex_color)
        _, _, l = ColorUtils.rgb_to_hsl(*rgb)

        if contrast_type == "text":
            # 文字对比：深色背景用浅色文字，浅色背景用深色文字
            if l > 0.5:
                return "#000000"  # 黑色
            else:
                return "#FFFFFF"  # 白色
        elif contrast_type == "background":
            # 背景对比：反转明度
            new_l = 1.0 - l
            new_rgb = ColorUtils.hsl_to_rgb(0, 0, new_l)  # 灰度
            return ColorUtils.rgb_to_hex(*new_rgb)
        else:
            # 互补色
            h, s, l = ColorUtils.rgb_to_hsl(*rgb)
            new_h = (h + 0.5) % 1.0
            new_rgb = ColorUtils.hsl_to_rgb(new_h, s, l)
            return ColorUtils.rgb_to_hex(*new_rgb)


# 测试函数
def test_color_utils():
    """测试色彩工具"""
    utils = ColorUtils

    # 测试基础转换
    hex_color = "#FF5733"
    rgb = utils.hex_to_rgb(hex_color)
    print(f"Hex: {hex_color} -> RGB: {rgb}")

    converted_back = utils.rgb_to_hex(*rgb)
    print(f"RGB: {rgb} -> Hex: {converted_back}")

    # 测试温度判断
    temp = utils.get_color_temperature("#FF5733")
    print(f"Color temperature: {temp}")

    # 测试调色板生成
    palette = utils.create_color_palette("#FF5733", "analogous")
    print(f"Analogous palette: {palette}")

    # 测试情绪调色板
    emotion_palette = utils.get_palette_for_emotion("happy")
    print(f"Happy palette: {emotion_palette}")

    # 测试文本颜色提取
    text = "她穿着红色的裙子，拿着蓝色的包"
    colors = utils.extract_color_from_text(text)
    print(f"Colors in text: {colors}")

    # 测试和谐度计算
    harmony_score = utils.calculate_color_harmony_score(["#FF0000", "#00FF00", "#0000FF"])
    print(f"Color harmony score: {harmony_score:.2f}")


if __name__ == "__main__":
    test_color_utils()
