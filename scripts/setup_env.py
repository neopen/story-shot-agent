#!/usr/bin/env python
"""
@FileName: app_env.py
@Description: 环境设置脚本
    负责检查Python环境、虚拟环境创建与激活、依赖安装等基础功能
        功能：
        1. 检查Python环境是否安装
        2. 检查虚拟环境是否存在，不存在则创建
        3. 根据不同系统激活虚拟环境
        4. 安装项目依赖
        5. 启动应用
    步骤严格按顺序执行，只有上一步成功才执行下一步
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/08 - 2025/11
"""

import os
import subprocess
import sys
import time
from abc import abstractmethod
from typing import final

from penshot.logger import debug, info, warning, error
from penshot.utils.env_utils import print_large_ascii
from penshot.utils.log_utils import print_log_exception

PROJECT_ROOT = "."

# 设置编码为UTF-8以确保中文显示正常
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")  # 虚拟环境目录
REQUIREMENTS_FILE = os.path.join(PROJECT_ROOT, "requirements.txt")  # 依赖文件


def ensure_directories():
    """确保必要的目录存在"""
    debug("=== 确保必要的目录存在 ===")


    return True


def get_virtual_environment_paths():
    """获取虚拟环境中Python、pip和activate命令的绝对路径"""
    if os.name == 'nt':  # Windows系统
        python_exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
        pip_exe = os.path.join(VENV_DIR, "Scripts", "pip.exe")
        activate_cmd = os.path.join(VENV_DIR, "Scripts", "activate")
    else:  # 非Windows系统
        python_exe = os.path.join(VENV_DIR, "bin", "python")
        pip_exe = os.path.join(VENV_DIR, "bin", "pip")
        activate_cmd = os.path.join(VENV_DIR, "bin", "activate")

    # 验证虚拟环境文件是否存在
    if not os.path.exists(python_exe):
        error(f"[错误] 虚拟环境Python解释器不存在！路径: {python_exe}")
        return None, None, None

    return python_exe, pip_exe, activate_cmd


class AppBaseEnv:
    """应用环境基类"""

    def __init__(self):
        """初始化环境"""
        self.python_exe = None
        self.pip_exe = None
        self.activate_cmd = None
        self.venv_dir = VENV_DIR
        self.requirements_file = REQUIREMENTS_FILE
        self.project_root = PROJECT_ROOT

    @final
    def run_command(self, command, shell=True, capture_output=False, check=False):
        """运行系统命令并返回结果"""
        try:
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=capture_output,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            error(f"[错误] 命令执行失败: {command}")
            error(f"[错误] 错误码: {e.returncode}")
            error(f"[错误] 错误输出: {e.stderr}")
            return e
        except Exception as e:
            error(f"[错误] 执行命令时发生异常: {command}")
            error(f"[错误] 异常信息: {str(e)}")
            return None

    @final
    def check_python_installation(self):
        """步骤1: 检查Python是否安装"""
        info("=== 检查Python环境 ===")
        result = self.run_command("python --version", capture_output=True)
        if result and hasattr(result, 'returncode') and result.returncode == 0:
            debug(f"[成功] Python环境检查通过: {result.stdout.strip()}")
            return True
        else:
            error("[错误] 未找到Python！请确保Python已正确安装并添加到系统PATH。")
            return False

    @final
    def create_virtual_environment(self):
        """步骤2: 检查并创建虚拟环境"""
        info("=== 检查虚拟环境 ===")
        if os.path.exists(VENV_DIR):
            debug(f"虚拟环境已存在于 '{VENV_DIR}'，检查有效性。")
            # 获取虚拟环境Python路径以验证虚拟环境是否有效
            if os.name == 'nt':  # Windows系统
                venv_python = os.path.join(VENV_DIR, "Scripts", "python.exe")
            else:  # 非Windows系统
                venv_python = os.path.join(VENV_DIR, "bin", "python")

            if os.path.isfile(venv_python):
                debug(f"[成功] 虚拟环境有效，使用现有虚拟环境。")
                return True
            else:
                warning(f"[警告] 虚拟环境无效，重新创建: {VENV_DIR}")
                import shutil
                shutil.rmtree(VENV_DIR)
        else:
            info(f"虚拟环境不存在于 '{VENV_DIR}'，创建新的虚拟环境。")

        info(f"在当前目录下创建Python虚拟环境 '{VENV_DIR}'...")
        result = self.run_command(f"python -m venv {VENV_DIR}")
        if result and hasattr(result, 'returncode') and result.returncode == 0:
            debug("[成功] 虚拟环境创建成功。")
            return True
        else:
            error("[错误] 虚拟环境创建失败！请检查权限和磁盘空间。")
            return False

    @staticmethod
    def activate_virtual_environment():
        """步骤3: 获取虚拟环境路径并验证可用性"""
        debug("=== 步骤3: 获取虚拟环境路径 ===")
        python_exe, pip_exe, activate_cmd = get_virtual_environment_paths()

        # 检查虚拟环境Python解释器是否存在
        if not python_exe:
            error("[错误] 无法获取虚拟环境路径。")
            return None, None

        # 检查虚拟环境Python解释器是否可执行
        if not os.access(python_exe, os.X_OK):
            error(f"[错误] 虚拟环境Python解释器不可执行: {python_exe}")
            return None, None

        # 检查虚拟环境pip是否可执行
        if not os.access(pip_exe, os.X_OK):
            error(f"[错误] 虚拟环境pip不可执行: {pip_exe}")
            return None, None

        debug(f"[成功] 虚拟环境验证通过，将使用以下路径：Python: {python_exe}")

        # 注意：在subprocess中执行activate命令不会影响当前进程的环境变量
        # 我们将直接使用虚拟环境的Python和pip完整路径来运行命令
        debug("提示：本脚本将直接使用虚拟环境的Python和pip完整路径执行后续操作，无需激活虚拟环境。")

        return python_exe, pip_exe

    @final
    def check_dependencies_satisfied(self, python_exe):
        """检查依赖是否满足"""
        try:
            debug("检查依赖是否满足...")
            # 尝试导入一些关键库来验证依赖是否安装正确
            test_imports = "import fastapi, requests, json, os, sys"
            result = self.run_command(f"{python_exe} -c \"{test_imports}\"", capture_output=True)

            if result and hasattr(result, 'returncode') and result.returncode != 0:
                # python.exe -m pip install --upgrade pip
                error(f"依赖检查失败: {result.stderr}")
                self.run_command(f"{python_exe} -m pip install --upgrade pip")
                return False

            debug("依赖检查通过")
            return True
        except Exception as e:
            error(f"检查依赖时出错: {str(e)}")
            return False

    @final
    def install_dependencies(self, pip_exe):
        """步骤4: 安装项目依赖"""
        info("=== 安装项目依赖 ===")
        if not os.path.exists(REQUIREMENTS_FILE):
            warning(f"[警告] 依赖文件 {REQUIREMENTS_FILE} 不存在！")
            return False

        debug(f"使用虚拟环境pip安装项目依赖包（{REQUIREMENTS_FILE}）...")

        # 使用虚拟环境的pip安装项目依赖
        result = self.run_command(f'"{pip_exe}" install -r "{REQUIREMENTS_FILE}"')
        # result = self.run_command(f'pip install -r requirements.txt"')
        if result and hasattr(result, 'returncode') and result.returncode == 0:
            debug("[成功] 依赖安装成功。")
            return True
        else:
            error("[错误] 依赖安装失败！")
            return False

    @final
    def start_aigc_application(self, max_retries=3):
        """步骤5: 启动FastAPI应用"""
        info("=== 启动FastAPI应用 ===")

        # 确保必要的目录存在
        if not ensure_directories():
            return False

        try:
            info("<<<<<<<<<<<<<<<<<<<<  Neopen 剧本分镜智能体 >>>>>>>>>>>>>>>>>>>>")
            info("应用启动中，请不要关闭此窗口。如果需要停止应用，请按 Ctrl+C")

            # 启动应用
            self.retries_start_application(max_retries)

            return True
        except subprocess.CalledProcessError as e:
            error(f"[错误] 应用启动失败: {e}")
            return False
        except KeyboardInterrupt:
            info("[信息] 应用已被用户中断。")
            return True
        except Exception as e:
            error(f"[错误] 发生未预期的错误: {e}")
            print_log_exception()
            return False

    @final
    def retries_start_application(self, max_retries=3):
        retry_count = 0

        while retry_count < max_retries:
            try:
                # 重新获取pip路径并安装依赖
                _, pip_exe_retry, _ = get_virtual_environment_paths()
                if not pip_exe_retry:
                    error("无法获取虚拟环境pip路径")
                    retry_count += 1
                    if retry_count < max_retries:
                        info(f"等待2秒后重试 ({retry_count}/{max_retries})\n")
                        time.sleep(2)
                        continue
                    else:
                        return False

                # 使用虚拟环境的Python启动Streamlit应用
                result = self.start_application()
                if result and hasattr(result, 'returncode') and result.returncode == 1:
                    if not self.install_dependencies(self):
                        error("依赖重新安装失败")
                    retry_count += 1
                    continue

                return result is not None
            except KeyboardInterrupt:
                info("应用已被用户中断。")
                return True
            except ModuleNotFoundError:
                error("缺少依赖模块，请检查requirements.txt")
                if not self.install_dependencies(self):
                    error("依赖重新安装失败")
                retry_count += 1

            except Exception as e:
                error(f"应用程序启动失败！,异常信息: {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    info(f"等待2秒后重试 ({retry_count}/{max_retries})\n")
                    time.sleep(2)
                else:
                    error("达到最大重试次数，启动失败")
                    return False

    @final
    def main(self, max_retries=3):
        """主函数 - 协调整个启动流程"""
        print_large_ascii()
        info("==================================================================")
        info("<                   欢迎使用 Neopen 剧本分镜智能体                 >")
        info("<           ⭐https://github.com/neopen/video-shot-agent       >")
        info("==================================================================")
        debug(f"当前工作目录: {os.getcwd()}")
        debug(f"将使用的虚拟环境: {VENV_DIR}")

        # 步骤1: 检查Python安装
        if not self.check_python_installation():
            input("按Enter键退出...")
            sys.exit(1)

        # 步骤2: 检查并创建虚拟环境
        if not self.create_virtual_environment():
            input("按Enter键退出...")
            sys.exit(1)

        # 步骤3: 激活虚拟环境
        python_exe, pip_exe = self.activate_virtual_environment()
        if not python_exe:
            input("按Enter键退出...")
            sys.exit(1)

        # 步骤4: 安装项目依赖
        # 先检查依赖是否已满足，如果满足则跳过安装
        if not self.check_dependencies_satisfied(python_exe):
            warning("依赖不满足，需要安装...")
            if not self.install_dependencies(pip_exe):
                input("按Enter键退出...")
                sys.exit(1)
        else:
            debug("依赖已满足，跳过安装步骤。")

        # 步骤5: 启动
        self.start_aigc_application(max_retries)

        info(">>>>>>>>>>>>>>>>> Neopen 剧本分镜智能体 <<<<<<<<<<<<<<<<<")
        info("应用程序已停止运行。按Enter键退出...")

    """    需要子类实现的抽象方法，用于启动具体的应用"""

    @abstractmethod
    def start_application(self):
        pass
