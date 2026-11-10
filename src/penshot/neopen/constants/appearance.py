"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: appearance.py
@Description: 角色外观词表：按语言分组，供 appearance_anchors 归类与排除
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

# 词表按语言分组维护：新增语言时只追加对应集合，提取规则无需改动。
# 中文按子串匹配；英文按单词边界匹配并容忍常见屈折后缀（见 contains_keyword）。

# 情绪 / 表情 / 表演 / 动作 / 道具词汇：命中即整句排除
EXCLUDE_KEYWORDS_ZH = frozenset(
    {
        "神情",
        "表情",
        "眼神",
        "焦急",
        "惊喜",
        "紧张",
        "微笑",
        "哭",
        "笑",
        "喊",
        "说",
        "道",
        "动作",
        "骑",
        "掏出",
        "拿出",
        "手持",
        "手拿",
        "拿着",
        "握",
        "抱",
        "推",
        "拉",
        "抓",
        "跑",
        "走",
        "蹲",
        "站",
        "坐",
        "擦",
        "低头",
        "抬头",
        "转身",
        "湿漉",
    }
)

EXCLUDE_KEYWORDS_EN = frozenset(
    {
        "smile",
        "grin",
        "laugh",
        "cry",
        "tears",
        "tearful",
        "frown",
        "scowl",
        "expression",
        "emotion",
        "emotional",
        "angry",
        "sad",
        "happy",
        "nervous",
        "anxious",
        "calm",
        "surprised",
        "shocked",
        "scared",
        "frightened",
        "excited",
        "confused",
        "determined",
        "hopeful",
        "gentle",
        "kind",
        "gaze",
        "stare",
        "look",
        "glance",
        "walk",
        "run",
        "ride",
        "hold",
        "carry",
        "grab",
        "wipe",
        "sitting",
        "standing",
        "kneeling",
        "crouching",
        "squatting",
        "leaning",
        "reach",
        "push",
        "pull",
        "entering",
        "leaving",
        "approach",
        "waving",
        "book",
        "notebook",
        "basketball",
        "ball",
        "phone",
        "pen",
        "umbrella",
        "letter",
        "cup",
        "bottle",
        "flower",
    }
)

EXCLUDE_KEYWORDS = EXCLUDE_KEYWORDS_ZH | EXCLUDE_KEYWORDS_EN

# 具体服装名词：用于识别“服装子句”，模糊的“装扮/outfit”不算
GARMENT_NOUNS_ZH = frozenset(
    {
        "外套",
        "大衣",
        "雨衣",
        "夹克",
        "风衣",
        "衬衫",
        "T恤",
        "卫衣",
        "毛衣",
        "背心",
        "西装",
        "制服",
        "长裤",
        "短裤",
        "裤",
        "裙",
        "鞋",
        "靴",
        "袜",
        "帽",
        "围巾",
        "手套",
    }
)

GARMENT_NOUNS_EN = frozenset(
    {
        "coat",
        "overcoat",
        "trench coat",
        "raincoat",
        "jacket",
        "blazer",
        "suit",
        "uniform",
        "shirt",
        "t-shirt",
        "tshirt",
        "blouse",
        "sweater",
        "jumper",
        "hoodie",
        "sweatshirt",
        "cardigan",
        "vest",
        "waistcoat",
        "dress",
        "gown",
        "skirt",
        "pants",
        "trousers",
        "jeans",
        "shorts",
        "leggings",
        "overalls",
        "robe",
        "apron",
        "scarf",
        "glove",
        "mitten",
        "shoe",
        "sneaker",
        "boot",
        "sandal",
        "sock",
        "hat",
        "cap",
        "beanie",
        "helmet",
        "belt",
        "tie",
        "swimsuit",
        "pajamas",
        "pyjamas",
    }
)

GARMENT_NOUNS = GARMENT_NOUNS_ZH | GARMENT_NOUNS_EN

# 外观状态词：湿/干/破损/褪色等，用于保留“肩头微湿”这类状态子句
STATE_KEYWORDS_ZH = frozenset({"湿", "干", "破", "脏", "褶皱", "褪色", "颜色", "色"})

STATE_KEYWORDS_EN = frozenset(
    {
        "wet",
        "damp",
        "soaked",
        "drenched",
        "dry",
        "torn",
        "ripped",
        "dirty",
        "stained",
        "wrinkled",
        "creased",
        "faded",
        "frayed",
        "patched",
        "color",
        "colored",
        "coloured",
    }
)

STATE_KEYWORDS = STATE_KEYWORDS_ZH | STATE_KEYWORDS_EN

HAIR_KEYWORDS_ZH = frozenset({"头发", "发型", "短发", "长发", "马尾", "辫", "刘海"})

HAIR_KEYWORDS_EN = frozenset(
    {
        "hair",
        "hairstyle",
        "ponytail",
        "braid",
        "pigtail",
        "bangs",
        "fringe",
        "bun",
        "curls",
        "curly",
        "bald",
        "dreadlocks",
    }
)

HAIR_KEYWORDS = HAIR_KEYWORDS_ZH | HAIR_KEYWORDS_EN

FACE_KEYWORDS_ZH = frozenset(
    {"脸", "面容", "面庞", "五官", "肤色", "皮肤", "眼", "眉", "唇"}
)

FACE_KEYWORDS_EN = frozenset(
    {
        "face",
        "facial",
        "complexion",
        "skin",
        "eyebrow",
        "eyelash",
        "lips",
        "nose",
        "cheekbone",
        "jawline",
        "freckles",
        "beard",
        "mustache",
        "moustache",
        "stubble",
        "mole",
        "scar",
    }
)

FACE_KEYWORDS = FACE_KEYWORDS_ZH | FACE_KEYWORDS_EN

BODY_KEYWORDS_ZH = frozenset({"身材", "体型", "高挑", "魁梧", "瘦", "胖", "匀称"})

BODY_KEYWORDS_EN = frozenset(
    {
        "build",
        "physique",
        "figure",
        "height",
        "slim",
        "slender",
        "thin",
        "muscular",
        "stocky",
        "plump",
        "petite",
        "athletic",
        "chubby",
        "lanky",
        "curvy",
        "broad-shouldered",
        "well-built",
    }
)

BODY_KEYWORDS = BODY_KEYWORDS_ZH | BODY_KEYWORDS_EN

ACCESSORY_KEYWORDS_ZH = frozenset(
    {
        "眼镜",
        "耳环",
        "项链",
        "手链",
        "戒指",
        "围巾",
        "手套",
        "帽子",
        "背包",
        "挎包",
        "发带",
    }
)

ACCESSORY_KEYWORDS_EN = frozenset(
    {
        "glasses",
        "sunglasses",
        "spectacles",
        "earring",
        "necklace",
        "bracelet",
        "ring",
        "backpack",
        "handbag",
        "purse",
        "hairband",
        "headband",
        "hair clip",
        "brooch",
        "watch",
        "wristwatch",
    }
)

ACCESSORY_KEYWORDS = ACCESSORY_KEYWORDS_ZH | ACCESSORY_KEYWORDS_EN

# 服装域与配饰域重叠的“围巾/手套/帽子/scarf/glove/hat”统一归服装，
# 避免同一服饰被判成两个语义域
ACCESSORY_ONLY_KEYWORDS = ACCESSORY_KEYWORDS - GARMENT_NOUNS

# 鞋袜类常被单独提及（如“湿漉的鞋”），不参与“整体服装是否更换”的判定
FOOTWEAR_KEYWORDS_ZH = frozenset({"鞋", "靴", "袜"})

FOOTWEAR_KEYWORDS_EN = frozenset({"shoe", "sneaker", "boot", "sandal", "sock"})

FOOTWEAR_KEYWORDS = FOOTWEAR_KEYWORDS_ZH | FOOTWEAR_KEYWORDS_EN

# 跨片段比较着装用的“主体服装”词：上装/下装/连衣裙等，
# 已排除鞋袜与同时属于配饰的围巾/手套/帽子
MAIN_GARMENT_KEYWORDS = GARMENT_NOUNS - ACCESSORY_KEYWORDS - FOOTWEAR_KEYWORDS
