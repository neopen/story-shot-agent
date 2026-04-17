"""
@FileName: enhanced_script_parser_example.py
@Description: 优化版剧本解析智能体使用示例
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2025/11
"""
import json
import os
import sys

from penshot.neopen.client.client_factory import get_default_llm

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from penshot.neopen.agent.script_parser_agent import ScriptParserAgent


def example_basic_script_parsing():
    """
    基础剧本解析示例
    将简单的中文剧本转换为结构化动作序列
    """
    print("=== 基础剧本解析示例 ===")

    # 初始化智能体（不需要LLM也可以工作）
    parser_agent = ScriptParserAgent(get_default_llm())

    # 简单的中文剧本示例
    script_text = """
    李明坐在城市咖啡馆靠窗的位置，悠闲地喝着咖啡。下午3点的阳光透过窗户洒在他身上，他看起来很平静。
    这时，一个年轻女子推门而入，四处张望。她看到李明后，走了过来。
    王小红：李明！你怎么在这里？
    李明抬起头，惊讶地看着王小红。
    李明：小红？真巧啊，我来这里见个朋友。
    王小红在李明对面坐下，表情有些复杂。
    王小红：其实...我是来找你的。
    """

    # 解析剧本
    structured_script = parser_agent.parser_process(script_text)

    # 打印结果
    print("\n解析结果：")
    print(json.dumps(structured_script, ensure_ascii=False, indent=2))

    return structured_script


def example_with_character_appearance():
    """
    角色外观推断示例
    展示如何推断角色的年龄、穿着和外貌特征
    """
    print("\n=== 角色外观推断示例 ===")

    parser_agent = ScriptParserAgent(get_default_llm())

    # 包含更多角色描述线索的剧本
    script_text = """
    地点：市中心商务大厦，时间：上午10点
    
    张经理穿着笔挺的西装，快步走进会议室。他看起来大约40岁，表情严肃。
    张经理：各位，我们今天要讨论新产品的发布计划。
    
    年轻的实习生小李坐在角落里，紧张地翻看着手中的文件。
    小李：经理，我...我准备好了市场分析报告。
    
    张经理点点头，示意小李继续。
    """

    structured_script = parser_agent.parser_process(script_text)

    print("\n角色外观信息：")
    for scene in structured_script.get("scenes", []):
        characters_info = scene.get("characters_info", {})
        print(f"场景 '{scene['location']}' 中的角色信息：")
        for character, appearance in characters_info.items():
            print(f"  - {character}: {appearance}")

    return structured_script


def example_emotion_recognition():
    """
    情绪识别示例
    展示如何从对话和动作中识别角色情绪
    """
    print("\n=== 情绪识别示例 ===")

    parser_agent = ScriptParserAgent(get_default_llm())

    # 包含丰富情绪表达的剧本
    script_text = """
    夜晚的街道上，风雨交加。
    
    陈小雨奔跑着，雨水打湿了她的头发和衣服。她看起来很害怕，不时回头张望。
    陈小雨：救命啊！有人吗？
    
    突然，一个黑影从巷子里冲出来，抓住了她的手臂。
    陌生人：别喊了！把钱包交出来！
    
    陈小雨颤抖着，眼泪混着雨水流了下来。
    陈小雨：请...请不要伤害我，钱包给你。
    """

    structured_script = parser_agent.parser_process(script_text)

    print("\n情绪识别结果：")
    for scene in structured_script.get("scenes", []):
        print(f"场景：{scene['location']} ({scene['time']})")
        for action in scene.get("actions", []):
            emotion = action.get("emotion", "未知")
            if "dialogue" in action:
                print(f"  - {action['character']} (对话): {action['dialogue']} [情绪: {emotion}]")
            else:
                print(f"  - {action['character']} (动作): {action['action']} [情绪: {emotion}]")

    return structured_script


def example_complex_scene_parsing():
    """
    复杂场景解析示例
    处理包含多个场景和多条线索的剧本
    """
    print("\n=== 复杂场景解析示例 ===")

    parser_agent = ScriptParserAgent(get_default_llm())

    # 复杂剧本示例，包含多个场景转换
    script_text = """
    场景一：城市公园，早晨
    阳光明媚，公园里有许多晨练的人。
    老周穿着运动服，在湖边打着太极拳。他动作缓慢而有力，显得很从容。
    
    场景二：办公室，下午
    李总监坐在办公桌前，皱着眉头看着电脑屏幕。桌上堆满了文件和报表。
    李总监：这个季度的业绩怎么又下滑了！
    他重重地拍了一下桌子，吓得秘书小张赶紧敲门进来。
    小张：总监，您找我？
    李总监深吸一口气，尽量让自己平静下来。
    李总监：去把销售部的王经理叫来，我要和他谈谈。
    """

    structured_script = parser_agent.parser_process(script_text)

    print("\n场景分割结果：")
    for i, scene in enumerate(structured_script.get("scenes", [])):
        print(f"\n场景 {i + 1}: {scene['location']} ({scene['time']})")
        print(f"氛围: {scene.get('atmosphere', '未知')}")
        print(f"动作数量: {len(scene.get('actions', []))}")

    return structured_script


def example_comprehensive_analysis():
    """
    综合分析示例
    展示完整的剧本解析、情绪识别和角色外观推断流程
    """
    print("\n=== 综合分析示例 ===")

    parser_agent = ScriptParserAgent(get_default_llm())

    # 综合剧本示例
    script_text = """
    李明是一名28岁的程序员，穿着休闲装，戴着眼镜。他正在一家叫做"遇见"的咖啡馆里等朋友。
    下午3点的阳光透过大玻璃窗洒进来，整个咖啡馆显得很温馨。
    李明端起咖啡杯，轻轻喝了一口，然后低头看了看手表。他看起来有些焦虑。
    
    就在这时，一位年轻漂亮的女孩推门而入。她穿着连衣裙，长发披肩，看起来很优雅。
    她环顾四周，看到李明后露出微笑，快步走了过来。
    王小红：不好意思，我来晚了！
    李明抬头看到王小红，脸上的焦虑立刻变成了惊喜。
    李明：没关系，我也刚到不久。快坐吧！
    王小红在李明对面坐下，两人相视一笑。
    王小红：你今天看起来有点不一样，是不是有什么好事？
    李明犹豫了一下，然后从口袋里掏出一个小盒子。
    李明：小红，我们认识三年了，我想...我想请你做我的女朋友！
    王小红惊讶地捂住嘴巴，眼睛里闪烁着泪花。
    王小红：李明...我...我愿意！
    李明高兴地握住王小红的手，两人都笑了。
    """

    # 完整解析流程
    print("开始解析剧本...")
    structured_script = parser_agent.parser_process(script_text)

    # 展示详细分析结果
    print("\n综合分析结果：")

    # 1. 场景信息
    print("\n1. 场景信息:")
    for scene in structured_script.get("scenes", []):
        print(f"  - 地点: {scene['location']}")
        print(f"  - 时间: {scene['time']}")
        print(f"  - 氛围: {scene.get('atmosphere', '未知')}")

    # 2. 角色信息
    print("\n2. 角色信息:")
    for scene in structured_script.get("scenes", []):
        if "characters_info" in scene:
            for character, info in scene["characters_info"].items():
                print(f"  - {character}:")
                for k, v in info.items():
                    print(f"    {k}: {v}")

    # 3. 情绪变化轨迹
    print("\n3. 情绪变化轨迹:")
    character_emotions = {}

    for scene in structured_script.get("scenes", []):
        for action in scene.get("actions", []):
            character = action.get("character", "未知")
            emotion = action.get("emotion", "未知")

            if character not in character_emotions:
                character_emotions[character] = []
            character_emotions[character].append(emotion)

    for character, emotions in character_emotions.items():
        print(f"  - {character}: {' → '.join(emotions)}")

    return structured_script


def main():
    """
    运行所有示例
    """
    print("\n===== 优化版剧本解析智能体示例 =====\n")

    try:
        # 运行各个示例
        example_basic_script_parsing()
        example_with_character_appearance()
        example_emotion_recognition()
        example_complex_scene_parsing()
        example_comprehensive_analysis()

        # 展示配置管理信息
        print("\n=== 配置管理信息 ===")
        print("配置内容:")
        print("1. scene_patterns - 场景识别正则表达式模式")
        print("2. dialogue_patterns - 对话识别正则表达式模式")
        print("3. action_emotion_map - 动作关键词到情绪的映射")
        print("4. time_keywords - 时间关键词映射")
        print("5. appearance_keywords - 角色外观关键词映射")
        print("6. location_keywords - 地点关键词映射")
        print("7. emotion_keywords - 情绪关键词扩展")
        print("8. atmosphere_keywords - 场景氛围关键词")

        print("\n===== 所有示例运行完成 =====")
        print("提示：")
        print("1. 要获得最佳效果，请确保安装了jieba库（pip install jieba）")
        print("2. 配置LLM（如GPT-4o）可以获得更准确的情绪识别和角色外观推断")
        print("3. 对于生产环境，建议使用实际的embedding model进行知识库增强")
        print("4. 您可以直接编辑配置文件来添加或修改关键词和映射关系")

    except Exception as e:
        print(f"运行示例时出错: {str(e)}")


if __name__ == "__main__":
    main()
