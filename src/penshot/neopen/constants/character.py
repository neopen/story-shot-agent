"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: character.py
@Description: 角色领域常量：各语言中表示“无角色/非角色”的占位词
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/10
"""

# 词表按语言分组维护：新增语言时只追加对应集合，
# 归一化逻辑（character_names.normalize_character_name）无需改动。
NON_CHARACTER_NAMES_ZH = frozenset(
    {
        "",
        "无",
        "无角色",
        "无人",
        "场景",
        "环境",
        "背景",
        "空镜",
        "空镜头",
        "画面",
        "镜头",
        "视角",
        "主观镜头",
        "旁白",
        "声音",
        "音效",
        "字幕",
        "道具",
        "物品",
        "人群",
    }
)

NON_CHARACTER_NAMES_EN = frozenset(
    {
        "none",
        "null",
        "n/a",
        "n.a.",
        "na",
        "unknown",
        "nobody",
        "no one",
        "noone",
        "not applicable",
        "-",
        "—",
        "–",
        "scene",
        "the scene",
        "empty scene",
        "empty shot",
        "establishing shot",
        "background",
        "environment",
        "narration",
        "voiceover",
        "voice-over",
        "v.o.",
        "off-screen",
        "sound",
        "sfx",
        "subtitle",
        "prop",
        "item",
        "crowd",
        "extras",
    }
)

NON_CHARACTER_NAMES = NON_CHARACTER_NAMES_ZH | NON_CHARACTER_NAMES_EN
