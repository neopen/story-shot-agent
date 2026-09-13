"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the mit license.
see license File For Details.

@FileName: cross_chunk_validator.py
@Description: 跨块一致性验证器
@Author: NeoPen
@Time: 2026/4/28 15:29
"""

from typing import List, Dict, Optional

from penshot.neopen.agent.continuity_guardian.consistency_contract import GlobalConsistencyContract


class CrossChunkValidator:
    """跨块一致性验证器"""

    def __init__(self):
        self.chunk_results: List[Dict] = []

    def validate_chunk_transition(self, prev_result: Dict, curr_result: Dict) -> List[Dict]:
        """验证两个块之间的过渡一致性"""
        issues = []

        # 1. 验证角色连续性
        prev_chars = set(prev_result.get('characters_in_chunk', []))
        curr_chars = set(curr_result.get('characters_in_chunk', []))

        # 角色突然消失
        missing_chars = prev_chars - curr_chars
        for char in missing_chars:
            issues.append({
                "type": "character_disappears",
                "character": char,
                "severity": "high",
                "suggestion": f"角色{char}在块间突然消失，检查是否有过渡"
            })

        # 角色突然出现
        new_chars = curr_chars - prev_chars
        for char in new_chars:
            # 检查是否是主要角色
            if char in prev_result.get('main_characters', []):
                issues.append({
                    "type": "character_appears_suddenly",
                    "character": char,
                    "severity": "medium",
                    "suggestion": f"主要角色{char}突然出现，需要铺垫"
                })

        # 2. 验证场景连续性
        prev_location = prev_result.get('last_location')
        curr_location = curr_result.get('first_location')

        if prev_location and curr_location and prev_location != curr_location:
            # 场景切换，检查是否有角色跟随
            common_chars = prev_chars & curr_chars
            if common_chars:
                issues.append({
                    "type": "scene_transition",
                    "from_location": prev_location,
                    "to_location": curr_location,
                    "characters": list(common_chars),
                    "severity": "low",
                    "suggestion": f"场景从{prev_location}切换到{curr_location}，角色{list(common_chars)}跟随"
                })

        return issues

    def merge_chunk_contracts(self, chunks_contracts: List[GlobalConsistencyContract]) -> Optional[GlobalConsistencyContract]:
        """合并多个块的契约"""
        if not chunks_contracts:
            return None

        merged = chunks_contracts[0]

        for contract in chunks_contracts[1:]:
            # 合并角色信息
            for name, char in contract.characters.items():
                if name not in merged.characters:
                    merged.characters[name] = char
                else:
                    # 合并出现场景
                    merged.characters[name].appearance_scenes.extend(char.appearance_scenes)
                    merged.characters[name].last_scene = max(
                        merged.characters[name].last_scene,
                        char.last_scene
                    )

            # 合并场景
            for num, scene in contract.scenes.items():
                if num not in merged.scenes:
                    merged.scenes[num] = scene

            # 合并风格锚点
            merged.style_anchor.update(contract.style_anchor)

        merged.version += 1
        return merged
