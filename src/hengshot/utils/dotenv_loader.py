"""
@FileName: dotenv_loader.py
@Description: 智能 .env 加载器 - 按优先级查找并加载配置
@Author: HengLine
@Time: 2026/3/6 22:17
"""
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict

from hengshot.logger import warning, debug, info, error


class DotEnvLoader:
    """智能 .env 文件加载器"""

    def __init__(self, package_name: str = "hengshot"):
        self.package_name = package_name
        self.loaded_paths: List[Path] = []
        self._dotenv_available = self._check_dotenv()

    def _check_dotenv(self) -> bool:
        """检查 python-dotenv 是否可用"""
        try:
            import dotenv
            return True
        except ImportError:
            warning("python-dotenv 未安装，无法加载 .env 文件。请运行: pip install python-dotenv")
            return False

    def find_dotenv_files(self) -> List[Path]:
        """
        按优先级查找所有可能的 .env 文件位置

        优先级（从高到低）：
        1. 当前工作目录: ./ .env
        2. 用户配置目录: ~/.config/hengshot/.env
        3. 包安装目录: site-packages/hengshot/.env
        4. 开发模式项目根目录: ../../.env
        """
        candidates: List[Path] = []

        # 1. 当前工作目录（最高优先级）
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists():
            candidates.append(cwd_env)

        # 2. 用户配置目录
        user_config_dir = self._get_user_config_dir()
        user_env = user_config_dir / ".env"
        if user_env.exists():
            candidates.append(user_env)

        # 3. 包内部（安装后）
        try:
            import importlib.resources as res
            # Python 3.9+
            with res.path(self.package_name, "__init__.py") as pkg_init:
                pkg_dir = pkg_init.parent
                pkg_env = pkg_dir / ".env"
                if pkg_env.exists():
                    candidates.append(pkg_env)
        except (ImportError, FileNotFoundError, AttributeError):
            pass

        # 4. 开发模式：项目根目录（向上查找）
        dev_env = self._find_dev_dotenv()
        if dev_env and dev_env not in candidates:
            candidates.append(dev_env)

        return candidates

    def _get_user_config_dir(self) -> Path:
        """获取用户配置目录（跨平台）"""
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", "~"))
        elif sys.platform == "darwin":
            base = Path("~/Library/Application Support")
        else:  # Linux
            base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config"))

        config_dir = (base / self.package_name).expanduser()
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _find_dev_dotenv(self) -> Optional[Path]:
        """开发模式：向上查找项目根目录的 .env"""
        try:
            import importlib.util
            spec = importlib.util.find_spec(self.package_name)
            if spec and spec.origin:
                pkg_dir = Path(spec.origin).parent

                # 向上查找 1-3 层
                for parent in [pkg_dir, pkg_dir.parent, pkg_dir.parent.parent]:
                    env_file = parent / ".env"
                    if env_file.exists():
                        return env_file
        except Exception:
            pass
        return None

    def load(self, override: bool = False) -> Dict[str, str]:
        """
        加载所有找到的 .env 文件

        参数:
            override: True=后加载的覆盖先加载的（默认）
                     False=先加载的优先（不被覆盖）

        返回:
            加载的环境变量字典
        """
        if not self._dotenv_available:
            return {}

        from dotenv import load_dotenv, dotenv_values

        loaded_values: Dict[str, str] = {}
        dotenv_files = self.find_dotenv_files()

        if not dotenv_files:
            warning("未找到任何 .env 文件")
            debug(f"   搜索位置:")
            debug(f"   - {Path.cwd() / '.env'}")
            debug(f"   - {self._get_user_config_dir() / '.env'}")
            return {}

        info(f"找到 {len(dotenv_files)} 个 .env 文件:")
        for i, path in enumerate(dotenv_files, 1):
            debug(f"   {i}. {path}")

        # 按优先级加载（从高到低）
        for path in dotenv_files:
            try:
                # 加载到环境变量
                load_dotenv(path, override=override)

                # 读取文件内容
                values = dotenv_values(path)
                loaded_values.update(values)

                self.loaded_paths.append(path)
                debug(f"已加载: {path.name} ({len(values)} 个变量)")

            except Exception as e:
                error(f"加载 {path} 失败: {e}")

        # 从环境变量读取所有值
        all_env = {k: v for k, v in os.environ.items() if k in loaded_values}

        debug(f"共加载 {len(all_env)} 个环境变量")
        return all_env

    def get_loaded_paths(self) -> List[Path]:
        """获取已加载的 .env 文件路径"""
        return self.loaded_paths

    def show_summary(self):
        """显示加载摘要"""
        debug("\n" + "=" * 60)
        debug(".env 加载摘要")
        debug("=" * 60)

        if not self.loaded_paths:
            warning("未加载任何 .env 文件")
            return

        info(f"\n已加载文件 ({len(self.loaded_paths)} 个):")
        for i, path in enumerate(self.loaded_paths, 1):
            debug(f"  {i}. {path}")

        debug(f"\n环境变量:")
        for key in sorted(os.environ.keys()):
            if key.startswith(("OPENAI", "QWEN", "DEEPSEEK", "OLLAMA", "API", "MODEL")):
                value = os.environ[key]
                masked = value[:4] + "***" if len(value) > 8 else "***"
                debug(f"  {key}: {masked}")

        debug("=" * 60)


# 全局加载器实例
_dotenv_loader: Optional[DotEnvLoader] = None


def load_dotenv(override: bool = False) -> Dict[str, str]:
    """
    加载 .env 文件（全局函数）

    使用示例:
        from hengshot.config import load_dotenv
        load_dotenv()  # 自动查找并加载
    """
    global _dotenv_loader
    if _dotenv_loader is None:
        _dotenv_loader = DotEnvLoader("hengshot")

    return _dotenv_loader.load(override=override)


def get_dotenv_loader() -> DotEnvLoader:
    """获取 .env 加载器实例"""
    global _dotenv_loader
    if _dotenv_loader is None:
        _dotenv_loader = DotEnvLoader("hengshot")
    return _dotenv_loader


def show_dotenv_summary():
    """显示 .env 加载摘要"""
    loader = get_dotenv_loader()
    loader.show_summary()


# 导出
__all__ = [
    "load_dotenv",
    "show_dotenv_summary",
    "get_dotenv_loader",
    "DotEnvLoader",
]
