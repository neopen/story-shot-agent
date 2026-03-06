"""
@FileName: start_flask.py
@Description: Flask服务器启动脚本，负责提供API接口
    功能：
        1. 检查Python环境是否安装
        2. 检查虚拟环境是否存在，不存在则创建
        3. 根据不同系统激活虚拟环境
        4. 安装项目依赖
        5. 启动Flask应用

    步骤严格按顺序执行，只有上一步成功才执行下一步
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/08 - 2025/11
"""
import argparse
import signal
import sys
from pathlib import Path

from scripts.setup_env import AppBaseEnv
from hengshot.app import app
from hengshot.config.config import settings
from hengshot.logger import debug, info, error, get_logging_manager
from hengshot.utils.log_utils import print_log_exception

# 设置编码为UTF-8以确保中文显示正常
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent / "src"))


# 全局变量 - uvicorn期望的格式为"模块名:应用实例名"，不需要路径分隔符
# APP_FILE = "./app:app"  # 应用入口路径

class HengLineApp(AppBaseEnv):
    """HengLine应用启动类"""

    def start_application(self):
        """启动应用的抽象方法"""
        info("正在启动 HengLine 应用......")

        # 设置信号处理函数
        def signal_handler(sig, frame):
            info("\n[信息] 收到中断信号，正在关闭服务器...")
            # 使用uvicorn的Config和Server类以便更好地控制服务器生命周期
            if hasattr(self, 'server'):
                self.server.should_exit = True
            sys.exit(0)

        try:
            import uvicorn

            # 注册信号处理
            signal.signal(signal.SIGINT, signal_handler)  # 处理Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # 处理终止信号

            # 解析命令行参数
            parser = argparse.ArgumentParser(description='HengLine应用启动脚本')
            parser.add_argument('--host', type=str, help='服务器监听地址')
            parser.add_argument('--port', type=int, help='服务器监听端口')
            args = parser.parse_args()

            # 从配置中获取API服务器参数，设置合理的默认值
            api_config = settings.api
            host = args.host if args.host else api_config.host  # 默认监听所有网络接口
            port = args.port if args.port else api_config.port  # 默认端口8000
            reload = api_config.reload  # 调试模式下启用热重载
            workers = api_config.workers  # 默认1个工作进程
            log_level = get_logging_manager().get_level("uvicorn").lower()

            # 当启用reload时，uvicorn不支持多进程模式，自动禁用workers参数
            # if reload and workers > 1:
            #     info("警告: 热重载模式(reload=True)不支持多进程，自动将workers设置为1")
            #     workers = 1

            # 输出启动信息
            debug(f"服务器配置: host={host}, port={port}, reload={reload}, workers={workers}")
            info(f"提示: 按 Ctrl+C 可以停止服务器")

            # 检查应用文件路径是否正确
            # 注意：这里使用字符串路径而不是检查文件存在，因为uvicorn会解析模块路径

            # 当workers=1时，使用更直接的方式以支持信号处理
            if workers == 1:
                # 使用uvicorn的Config和Server类以获得更好的控制
                config = uvicorn.Config(
                    # APP_FILE,
                    app,
                    host=host,
                    port=port,
                    reload=False,
                    log_level=log_level,
                    access_log=True
                )
                server = uvicorn.Server(config)
                server.run()
            else:
                # 多进程模式下使用传统方式（此时reload一定为False）
                uvicorn.run(
                    app,
                    host=host,
                    port=port,
                    reload=False,  # 确保在多进程模式下reload为False
                    workers=workers,
                    log_level=log_level,
                    access_log=True
                )

            return True
        except ImportError:
            error("[错误] 未找到uvicorn模块，请确保已安装所有依赖。")
            return False
        except KeyboardInterrupt:
            debug("[信息] 应用已被用户中断。")
            return True
        except Exception as e:
            error(f"[错误] 发生未预期的错误: {e}")
            print_log_exception()
            return False


if __name__ == "__main__":
    HengLineApp().main()
