"""
@FileName: continuity_guardian_agent.py
@Description: 连续性守护智能体，负责跟踪角色状态，生成/验证连续性锚点
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/10 - 2025/11
"""
from typing import Dict, List, Optional, Any

from penshot.neopen.agent import ContinuityGuardianAgent


# 工作流调用接口
class ContinuityWorkflowInterface:
    """连续性工作流调用接口"""

    @staticmethod
    def create_agent(project_name: str, config: Optional[Dict] = None) -> ContinuityGuardianAgent:
        """
        创建连续性守护智能体

        Args:
            project_name: 项目名称
            config: 配置字典

        Returns:
            初始化后的智能体
        """
        agent = ContinuityGuardianAgent(project_name, config)
        agent.initialize()
        return agent

    @staticmethod
    def process_video_scene(agent: ContinuityGuardianAgent,
                            scene_data: Dict) -> Dict[str, Any]:
        """
        处理视频场景

        Args:
            agent: 连续性守护智能体
            scene_data: 场景数据

        Returns:
            处理结果
        """
        return agent.process(scene_data)

    @staticmethod
    def process_video_sequence(agent: ContinuityGuardianAgent,
                               scene_sequence: List[Dict]) -> Dict[str, Any]:
        """
        处理视频序列

        Args:
            agent: 连续性守护智能体
            scene_sequence: 场景序列

        Returns:
            序列处理结果
        """
        return agent.process_sequence(scene_sequence)

    @staticmethod
    def analyze_scene_transition(agent: ContinuityGuardianAgent,
                                 from_scene: Dict,
                                 to_scene: Dict) -> Dict[str, Any]:
        """
        分析场景转场

        Args:
            agent: 连续性守护智能体
            from_scene: 来源场景
            to_scene: 目标场景

        Returns:
            转场分析结果
        """
        return agent.analyze_transition(from_scene, to_scene)

    @staticmethod
    def generate_continuity_constraints(agent: ContinuityGuardianAgent,
                                        scene_data: Dict,
                                        scene_type: str = "general") -> Dict[str, Any]:
        """
        生成连续性约束

        Args:
            agent: 连续性守护智能体
            scene_data: 场景数据
            scene_type: 场景类型

        Returns:
            约束生成结果
        """
        return agent.generate_constraints(scene_data, scene_type)

    @staticmethod
    def validate_scene_physics(agent: ContinuityGuardianAgent,
                               scene_data: Dict) -> Dict[str, Any]:
        """
        验证场景物理

        Args:
            agent: 连续性守护智能体
            scene_data: 场景数据

        Returns:
            物理验证结果
        """
        return agent.validate_physics(scene_data)

    @staticmethod
    def get_continuity_report(agent: ContinuityGuardianAgent,
                              detailed: bool = True) -> Dict[str, Any]:
        """
        获取连续性报告

        Args:
            agent: 连续性守护智能体
            detailed: 是否详细

        Returns:
            连续性报告
        """
        return agent.get_continuity_report(detailed)

    @staticmethod
    def export_agent_session(agent: ContinuityGuardianAgent,
                             export_path: Optional[str] = None) -> Dict[str, Any]:
        """
        导出智能体会话

        Args:
            agent: 连续性守护智能体
            export_path: 导出路径

        Returns:
            导出结果
        """
        return agent.export_session(export_path)

    @staticmethod
    def reset_agent_session(agent: ContinuityGuardianAgent,
                            new_project_name: Optional[str] = None):
        """
        重置智能体会话

        Args:
            agent: 连续性守护智能体
            new_project_name: 新项目名称
        """
        agent.reset_session(new_project_name)


# 快速使用函数
def quick_continuity_check(scene_data: Dict,
                           config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    快速连续性检查

    Args:
        scene_data: 场景数据
        config: 配置字典

    Returns:
        检查结果
    """
    agent = ContinuityGuardianAgent("quick_check", config)
    agent.initialize()

    result = agent.process(scene_data)

    # 提取关键信息
    summary = {
        "scene_id": scene_data.get("scene_id", "unknown"),
        "continuity_score": result.get("physics_validation", {}).get("plausibility_score", 0.0),
        "issues_found": len(result.get("issues_by_frame", [])),
        "constraints_generated": result.get("constraints_generated", 0),
        "processing_time": result.get("processing_time", 0)
    }

    return summary


# 使用示例
def demonstrate_workflow():
    """演示工作流调用"""
    print("连续性守护智能体工作流演示")
    print("=" * 60)

    # 1. 创建智能体
    config = {
        "mode": "adaptive",
        "analysis_depth": "standard",
        "enable_auto_fix": True,
        "validation_frequency": 5
    }

    agent = ContinuityWorkflowInterface.create_agent(
        "demo_movie_project",
        config
    )

    print("1. 智能体创建完成")

    # 2. 准备测试场景
    test_scene = {
        "scene_id": "test_scene_001",
        "scene_type": "action",
        "frame_number": 1,
        "characters": [
            {
                "id": "hero",
                "name": "主角",
                "position": [0, 0, 0],
                "velocity": [1, 0, 0],
                "action": "running"
            }
        ],
        "environment": {
            "time_of_day": "day",
            "weather": "clear"
        }
    }

    # 3. 处理场景
    result = ContinuityWorkflowInterface.process_video_scene(agent, test_scene)
    print(f"2. 场景处理完成 - 处理时间: {result.get('processing_time', 0):.3f}秒")

    # 4. 生成约束
    constraints_result = ContinuityWorkflowInterface.generate_continuity_constraints(
        agent, test_scene, "action"
    )
    print(f"3. 约束生成完成 - 生成 {constraints_result.get('summary', {}).get('total_constraints', 0)} 个约束")

    # 5. 验证物理
    physics_result = ContinuityWorkflowInterface.validate_scene_physics(agent, test_scene)
    print(f"4. 物理验证完成 - 合理性分数: {physics_result.get('plausibility_score', 0):.2f}")

    # 6. 获取报告
    report = ContinuityWorkflowInterface.get_continuity_report(agent, detailed=False)
    print(f"5. 连续性报告生成完成 - 连续性分数: {report.get('continuity_score', 0):.2f}")

    # 7. 导出会话
    export_result = ContinuityWorkflowInterface.export_agent_session(agent)
    if export_result.get("success"):
        print(f"6. 会话导出完成 - 保存到: {export_result.get('export_path')}")

    print("\n" + "=" * 60)
    print("工作流演示完成")

    return agent, result


if __name__ == "__main__":
    # 运行演示
    agent, result = demonstrate_workflow()

    # 显示结果摘要
    print("\n结果摘要:")
    print(f"  场景ID: {result.get('frame_data', {}).get('scene_id', 'unknown')}")
    print(f"  物理合理性: {result.get('physics_validation', {}).get('plausibility_score', 0):.2f}")
    print(f"  约束数量: {result.get('constraints_generated', 0)}")
    print(f"  处理时间: {result.get('processing_time', 0):.3f}秒")
