"""
@FileName: cli.py
@Description: 命令行工具 - Penshot 智能分镜生成
使用方式:
    penshot --help
    penshot breakdown "剧本内容" -o output.json
    penshot breakdown -f script.txt -o result.json
    penshot serve          # 启动 MCP 服务器
    penshot serve-rest     # 启动 REST API 服务器
    penshot status <task_id>      # 查询任务状态
    penshot result <task_id>      # 获取任务结果
    penshot cancel <task_id>      # 取消任务
    penshot batch -f scripts.txt  # 批量处理
@Author: HiPeng
@Time: 2026/3/23 18:56
"""

import argparse
import json
import sys
import time
from typing import Dict

from penshot.api import PenshotFunction, ShotLanguage, __version__
from penshot.neopen.task.task_models import TaskStatus


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_colored(text: str, color: str = Colors.END):
    """彩色打印"""
    print(f"{color}{text}{Colors.END}")


def print_success(text: str):
    """打印成功信息"""
    print_colored(f"✓ {text}", Colors.GREEN)


def print_error(text: str):
    """打印错误信息"""
    print_colored(f"✗ {text}", Colors.RED)


def print_warning(text: str):
    """打印警告信息"""
    print_colored(f"⚠ {text}", Colors.YELLOW)


def print_info(text: str):
    """打印信息"""
    print_colored(f"ℹ {text}", Colors.BLUE)


def print_header(text: str):
    """打印标题"""
    print_colored(f"\n{'=' * 60}\n{text}\n{'=' * 60}", Colors.HEADER)


def read_script_from_file(file_path: str) -> str:
    """从文件读取剧本"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print_error(f"文件不存在: {file_path}")
        sys.exit(1)
    except Exception as e:
        print_error(f"读取文件失败: {str(e)}")
        sys.exit(1)


def save_result_to_file(result, output_path: str):
    """保存结果到文件"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print_success(f"结果已保存到: {output_path}")
    except Exception as e:
        print_error(f"保存失败: {str(e)}")


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}分{secs:.0f}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}小时{minutes}分"


def format_progress_bar(progress: float, width: int = 30) -> str:
    """格式化进度条"""
    filled = int(width * progress / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {progress:.1f}%"


def wait_for_task_with_progress(
        agent: PenshotFunction,
        task_id: str,
        timeout: float = 300,
        poll_interval: float = 1.0
) -> Dict:
    """等待任务完成并显示进度"""
    print_info(f"任务ID: {task_id}")
    print_info(f"开始处理... (超时时间: {format_duration(timeout)})")

    start_time = time.time()
    last_progress = -1

    while time.time() - start_time < timeout:
        task = agent.get_task_status(task_id)

        if not task:
            print_error("任务不存在")
            return {"success": False, "error": "任务不存在"}

        status = task.get("status")
        progress = task.get("progress", 0)

        # 显示进度
        if progress != last_progress and progress > 0:
            bar = format_progress_bar(progress)
            print(f"\r{bar} {progress:.1f}%", end="", flush=True)
            last_progress = progress

        if status == "completed" or status == TaskStatus.SUCCESS:
            print()  # 换行
            print_success(f"任务完成！耗时: {format_duration(time.time() - start_time)}")
            result = agent.get_task_result(task_id)
            return {"success": True, "result": result}

        if status == "failed" or status == TaskStatus.FAILED:
            print()  # 换行
            error_msg = task.get("error", "未知错误")
            print_error(f"任务失败: {error_msg}")
            return {"success": False, "error": error_msg}

        if status == "cancelled" or status == TaskStatus.CANCELLED:
            print()  # 换行
            print_warning("任务已取消")
            return {"success": False, "error": "任务已取消"}

        time.sleep(poll_interval)

    print()  # 换行
    print_error(f"等待超时 ({format_duration(timeout)})")
    return {"success": False, "error": "等待超时"}


def cmd_breakdown(args):
    """执行分镜拆分命令"""
    print_header("Penshot - 智能分镜生成")

    # 读取剧本
    if args.file:
        script = read_script_from_file(args.file)
        print_info(f"从文件读取剧本: {args.file} ({len(script)}字符)")
    else:
        script = args.script
        print_info(f"剧本长度: {len(script)}字符")

    # 创建智能体
    language = ShotLanguage.ZH if args.language == "zh" else ShotLanguage.EN
    agent = PenshotFunction(language=language, max_concurrent=5)

    # 执行分镜
    print_info("正在处理...")

    if args.sync:
        # 同步模式
        result = agent.breakdown_script(script, wait_timeout=args.timeout)

        if result.success:
            print_success("分镜生成成功")

            # 统计信息
            data = result.data or {}
            stats = data.get("stats", {})
            shots = data.get("shots", [])

            print_info(f"镜头数量: {stats.get('shot_count', len(shots))}")
            print_info(f"总时长: {stats.get('total_duration', 0):.1f}秒")
            print_info(f"处理时间: {result.processing_time_ms}ms")

            # 输出结果
            output_data = {
                "task_id": result.task_id,
                "success": True,
                "shots_count": stats.get("shot_count", len(shots)),
                "total_duration": stats.get("total_duration", 0),
                "shots": shots[:10] if args.verbose else shots[:3],
                "full_result": data if args.verbose else None
            }

            if args.output:
                save_result_to_file(output_data, args.output)
            else:
                print("\n预览 (前3个镜头):")
                for i, shot in enumerate(shots[:3], 1):
                    desc = shot.get('description', '无描述')
                    print(f"  {i}. {desc[:80]}..." if len(desc) > 80 else f"  {i}. {desc}")

                if args.verbose:
                    print("\n完整结果:")
                    print(json.dumps(output_data, ensure_ascii=False, indent=2))
        else:
            print_error(f"分镜生成失败: {result.error}")
            sys.exit(1)
    else:
        # 异步模式
        task_id = agent.breakdown_script_async(script)
        print_info(f"任务已提交: {task_id}")
        print_info(f"查询状态: penshot status {task_id}")
        print_info(f"获取结果: penshot result {task_id}")

        if args.wait:
            # 等待完成
            result = wait_for_task_with_progress(agent, task_id, timeout=args.timeout)
            if result.get("success"):
                r = result["result"]
                print_success(f"任务完成，结果: {r.task_id}")
            else:
                sys.exit(1)


def cmd_status(args):
    """查询任务状态"""
    agent = PenshotFunction(max_concurrent=5)
    task = agent.get_task_status(args.task_id)

    if not task:
        print_error(f"任务不存在: {args.task_id}")
        sys.exit(1)

    status = task.get("status", "unknown")
    stage = task.get("stage", "unknown")
    progress = task.get("progress", 0)
    created_at = task.get("created_at")
    updated_at = task.get("updated_at")

    print_header(f"任务状态: {args.task_id}")
    print(f"状态: {status}")
    print(f"阶段: {stage}")

    if progress > 0:
        print(f"进度: {progress:.1f}%")
        print(format_progress_bar(progress))

    if created_at:
        print(f"创建时间: {created_at}")
    if updated_at:
        print(f"更新时间: {updated_at}")

    if status in ["failed", TaskStatus.FAILED]:
        error_msg = task.get("error")
        if error_msg:
            print_error(f"错误: {error_msg}")

    if status in ["completed", TaskStatus.SUCCESS]:
        print_success("任务已完成")
    elif status in ["processing", TaskStatus.PROCESSING]:
        print_info("任务处理中")
    elif status in ["pending", TaskStatus.PENDING]:
        print_info("任务等待中")


def cmd_result(args):
    """获取任务结果"""
    agent = PenshotFunction(max_concurrent=5)
    result = agent.get_task_result(args.task_id)

    if not result:
        print_error(f"任务不存在或未完成: {args.task_id}")
        sys.exit(1)

    if not result.success:
        print_error(f"任务失败: {result.error}")
        sys.exit(1)

    print_header(f"任务结果: {args.task_id}")
    print_success(f"处理成功 (耗时: {result.processing_time_ms}ms)")

    data = result.data or {}
    stats = data.get("stats", {})
    shots = data.get("shots", [])

    print(f"\n统计信息:")
    print(f"  镜头数量: {stats.get('shot_count', len(shots))}")
    print(f"  总时长: {stats.get('total_duration', 0):.1f}秒")
    print(f"  对话数量: {stats.get('dialogue_count', 0)}")
    print(f"  动作数量: {stats.get('action_count', 0)}")

    print(f"\n镜头列表:")
    for i, shot in enumerate(shots[:args.limit], 1):
        print(f"\n  {i}. [{shot.get('shot_type', 'medium')}] {shot.get('description', '无描述')}")
        print(f"     时长: {shot.get('duration', 0):.1f}秒")
        if shot.get('main_character'):
            print(f"     角色: {shot.get('main_character')}")

    if len(shots) > args.limit:
        print(f"\n  ... 还有 {len(shots) - args.limit} 个镜头")

    if args.output:
        save_result_to_file(data, args.output)


def cmd_cancel(args):
    """取消任务"""
    agent = PenshotFunction(max_concurrent=5)
    success = agent.cancel_task(args.task_id)

    if success:
        print_success(f"任务已取消: {args.task_id}")
    else:
        print_error(f"取消失败: 任务不存在或已完成")


def cmd_batch(args):
    """批量处理"""
    print_header("Penshot - 批量分镜生成")

    # 读取剧本列表
    scripts = []
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        scripts.append(line)
        except FileNotFoundError:
            print_error(f"文件不存在: {args.file}")
            sys.exit(1)
        except Exception as e:
            print_error(f"读取文件失败: {str(e)}")
            sys.exit(1)
    elif args.scripts:
        scripts = args.scripts
    else:
        print_error("请提供剧本列表 (--file 或直接提供)")
        sys.exit(1)

    print_info(f"批量处理 {len(scripts)} 个剧本")

    language = ShotLanguage.ZH if args.language == "zh" else ShotLanguage.EN
    agent = PenshotFunction(language=language, max_concurrent=5)

    # 执行批量处理
    if args.sync:
        results = agent.batch_breakdown(scripts, wait_timeout=args.timeout)

        success_count = sum(1 for r in results if r.success)
        print_header("批量处理完成")
        print(f"成功: {success_count}/{len(scripts)}")

        for i, result in enumerate(results, 1):
            if result.success:
                data = result.data or {}
                stats = data.get("stats", {})
                print_success(f"  {i}. 成功 - {stats.get('shot_count', 0)}个镜头")
            else:
                print_error(f"  {i}. 失败 - {result.error}")

        if args.output:
            output_data = [
                {
                    "index": i,
                    "success": r.success,
                    "task_id": r.task_id,
                    "shots_count": r.data.get("stats", {}).get("shot_count") if r.data else 0,
                    "error": r.error
                }
                for i, r in enumerate(results, 1)
            ]
            save_result_to_file(output_data, args.output)
    else:
        # 异步批量提交
        task_ids = []
        for script in scripts:
            task_id = agent.breakdown_script_async(script)
            task_ids.append(task_id)

        print_info(f"已提交 {len(task_ids)} 个任务:")
        for i, tid in enumerate(task_ids, 1):
            print(f"  {i}. {tid}")

        if args.wait:
            print_info("等待所有任务完成...")
            results = []
            for tid in task_ids:
                result = wait_for_task_with_progress(agent, tid, timeout=args.timeout)
                if result.get("success"):
                    results.append(result["result"])
                else:
                    results.append(None)

            success_count = sum(1 for r in results if r and r.success)
            print_header(f"完成: {success_count}/{len(task_ids)}")


def cmd_serve(args):
    """启动 MCP 服务器"""
    print_header("Penshot MCP Server")
    print_info("启动中... (按 Ctrl+C 停止)")

    try:
        from penshot.mcp_server import run_mcp_server
        run_mcp_server()
    except KeyboardInterrupt:
        print("\n")
        print_warning("服务器已停止")
    except ImportError as e:
        print_error(f"导入 MCP 模块失败: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print_error(f"启动失败: {str(e)}")
        sys.exit(1)


def cmd_serve_rest(args):
    """启动 REST API 服务器"""
    print_header("Penshot REST API Server")
    print_info(f"启动中... http://{args.host}:{args.port}")
    print_info("按 Ctrl+C 停止")

    try:
        # 导入并启动 FastAPI 应用
        from penshot.app import app
        import uvicorn

        # 配置 uvicorn 服务器
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n")
        print_warning("服务器已停止")
    except ImportError as e:
        print_error(f"导入 FastAPI 模块失败: {str(e)}")
        print_info("请确保已安装 fastapi 和 uvicorn")
        sys.exit(1)
    except Exception as e:
        print_error(f"启动失败: {str(e)}")
        sys.exit(1)


def cmd_queue_status(args):
    """查看队列状态"""
    agent = PenshotFunction(max_concurrent=5)
    queue_status = agent.get_queue_status()
    stats = agent.get_stats()

    print_header("Penshot - 队列状态")
    print(f"\n队列状态:")
    print(f"  队列长度: {queue_status.get('queue_length', 0)}")
    print(f"  等待任务数: {queue_status.get('queue_waiting', 0)}")
    print(f"  活跃任务数: {queue_status.get('active_tasks', 0)}")
    print(f"  最大并发数: {queue_status.get('max_concurrent', 0)}")
    print(f"  队列使用率: {queue_status.get('queue_usage_percent', 0):.1f}%")

    print(f"\n统计信息:")
    print(f"  总提交: {stats.get('total_submitted', 0)}")
    print(f"  已完成: {stats.get('total_completed', 0)}")
    print(f"  失败: {stats.get('total_failed', 0)}")
    print(f"  已取消: {stats.get('total_cancelled', 0)}")
    print(f"  平均等待时间: {stats.get('avg_wait_time_ms', 0):.0f}ms")


def cmd_version(args):
    """显示版本信息"""
    print(f"Penshot v{__version__}")
    print(f"作者: HiPeng")
    print(f"GitHub: https://github.com/neopen/story-shot-agent")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Penshot - 智能分镜视频生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  penshot breakdown "深夜，客厅里，张三紧张地环顾四周..." -o result.json
  penshot breakdown -f script.txt --sync -o result.json
  penshot status <task_id>
  penshot result <task_id> -o output.json
  penshot cancel <task_id>
  penshot batch -f scripts.txt --sync
  penshot serve-rest --port 8080
  penshot queue-status
        """
    )

    parser.add_argument(
        '-v', '--version',
        action='store_true',
        help='显示版本信息'
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # breakdown 命令
    breakdown_parser = subparsers.add_parser('breakdown', help='剧本分镜拆分')
    input_group = breakdown_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('script', nargs='?', help='剧本文本')
    input_group.add_argument('-f', '--file', help='从文件读取剧本')
    breakdown_parser.add_argument('-o', '--output', help='输出文件路径')
    breakdown_parser.add_argument('--language', default='zh', choices=['zh', 'en'], help='输出语言')
    breakdown_parser.add_argument('--sync', action='store_true', help='同步模式（等待完成）')
    breakdown_parser.add_argument('--wait', action='store_true', help='异步模式等待完成')
    breakdown_parser.add_argument('--timeout', type=float, default=300, help='超时时间（秒）')
    breakdown_parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')

    # status 命令
    status_parser = subparsers.add_parser('status', help='查询任务状态')
    status_parser.add_argument('task_id', help='任务ID')

    # result 命令
    result_parser = subparsers.add_parser('result', help='获取任务结果')
    result_parser.add_argument('task_id', help='任务ID')
    result_parser.add_argument('-o', '--output', help='输出文件路径')
    result_parser.add_argument('--limit', type=int, default=10, help='显示镜头数量限制')

    # cancel 命令
    cancel_parser = subparsers.add_parser('cancel', help='取消任务')
    cancel_parser.add_argument('task_id', help='任务ID')

    # batch 命令
    batch_parser = subparsers.add_parser('batch', help='批量处理')
    input_group = batch_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-f', '--file', help='剧本列表文件（每行一个剧本）')
    input_group.add_argument('scripts', nargs='*', help='多个剧本文本')
    batch_parser.add_argument('-o', '--output', help='输出文件路径')
    batch_parser.add_argument('--language', default='zh', choices=['zh', 'en'], help='输出语言')
    batch_parser.add_argument('--sync', action='store_true', help='同步模式')
    batch_parser.add_argument('--wait', action='store_true', help='异步模式等待完成')
    batch_parser.add_argument('--timeout', type=float, default=600, help='超时时间（秒）')

    # queue-status 命令
    queue_parser = subparsers.add_parser('queue-status', help='查看队列状态')

    # serve 命令
    serve_parser = subparsers.add_parser('serve', help='启动 MCP 服务器')

    # serve-rest 命令
    rest_parser = subparsers.add_parser('serve-rest', help='启动 REST API 服务器')
    rest_parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    rest_parser.add_argument('--port', type=int, default=8000, help='监听端口')

    return parser


def main():
    """主入口"""
    parser = create_parser()
    args = parser.parse_args()

    # 版本信息
    if args.version:
        cmd_version(args)
        return

    # 无命令时显示帮助
    if not args.command:
        parser.print_help()
        return

    # 执行命令
    command_map = {
        'breakdown': cmd_breakdown,
        'status': cmd_status,
        'result': cmd_result,
        'cancel': cmd_cancel,
        'batch': cmd_batch,
        'queue-status': cmd_queue_status,
        'serve': cmd_serve,
        'serve-rest': cmd_serve_rest,
    }

    if args.command in command_map:
        command_map[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
