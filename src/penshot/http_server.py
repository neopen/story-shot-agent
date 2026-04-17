"""
@FileName: http_server.py
@Description: Penshot HTTP 服务 - 可直接在命令行启动
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/3/30
"""

import argparse
import signal
import sys
from pathlib import Path

# 设置编码为UTF-8以确保中文显示正常
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from penshot.config.config import settings
from penshot.logger import debug, info, error, get_logging_manager
from penshot.utils.log_utils import print_log_exception
from penshot.app.setup_env import AppBaseEnv


class HttpServer(AppBaseEnv):
    """Penshot HTTP 服务启动类"""

    def start_application(self):
        """启动应用"""
        info("正在启动 Penshot 服务......")

        # 设置信号处理函数
        def signal_handler(sig, frame):
            info("\n收到中断信号，正在关闭服务器...")
            if hasattr(self, 'server'):
                self.server.should_exit = True
            sys.exit(0)

        try:
            import uvicorn

            # 注册信号处理
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # 解析命令行参数
            parser = argparse.ArgumentParser(description='Penshot 服务启动脚本')
            parser.add_argument('--host', type=str, help='服务器监听地址')
            parser.add_argument('--port', type=int, help='服务器监听端口')
            parser.add_argument('--max-concurrent', type=int, default=10, help='最大并发数')
            parser.add_argument('--queue-size', type=int, default=1000, help='队列大小')
            parser.add_argument('--reload', action='store_true', help='开发模式自动重载')
            args = parser.parse_args()

            # 从配置中获取API服务器参数
            api_config = settings.api
            host = args.host if args.host else api_config.host
            port = args.port if args.port else api_config.port
            log_level = get_logging_manager().get_level("uvicorn").lower()
            reload = args.reload

            # 导入应用
            # 注意：penshot/app/application.py 中的 app 是 FastAPI 实例
            from penshot.app.application import app as penshot_app

            # 如果需要传递并发参数，可以在应用启动时设置
            # 这里通过环境变量或 settings 传递
            import os
            os.environ['PENSHOT_MAX_CONCURRENT'] = str(args.max_concurrent)
            os.environ['PENSHOT_QUEUE_SIZE'] = str(args.queue_size)

            # 输出启动信息
            print("\n" + "=" * 60)
            print("Penshot 分镜生成服务")
            print("=" * 60)
            print(f"服务地址: http://{host}:{port}")
            print(f"最大并发: {args.max_concurrent}")
            print(f"队列大小: {args.queue_size}")
            print("")
            print("API 端点:")
            print(f"  POST /api/v1/storyboard     - 提交剧本生成分镜")
            print(f"  GET  /api/v1/status/{{id}}  - 查询任务状态")
            print(f"  GET  /api/v1/result/{{id}}  - 获取任务结果")
            print(f"  POST /api/v1/cancel/{{id}}  - 取消任务")
            print("")
            print("按 Ctrl+C 停止服务器")
            print("=" * 60 + "\n")

            # 启动服务
            config = uvicorn.Config(
                penshot_app,
                host=host,
                port=port,
                reload=reload,
                log_level=log_level,
                access_log=True
            )
            server = uvicorn.Server(config)
            self.server = server
            server.run()

            return True

        except ImportError as e:
            error(f"导入错误: {e}")
            error("请确保已安装所有依赖: pip install -r requirements.txt")
            return False
        except KeyboardInterrupt:
            debug("服务已被用户中断。")
            return True
        except Exception as e:
            error(f"启动失败: {e}")
            print_log_exception()
            return False


if __name__ == "__main__":
    HttpServer().main()
