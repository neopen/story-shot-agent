"""测试日志文件隔离开关（FR-0.4.7 日志可观测性）

覆盖：``PENSHOT_LOG_TO_FILE`` 关闭文件日志、``PENSHOT_LOG_FILE`` 覆盖路径，
保证 pytest 输出不再写入生产日志文件。
"""

from penshot.logger import LoggingConfigManager


def test_file_logging_disabled_by_env(monkeypatch):
    """PENSHOT_LOG_TO_FILE=0 时不注册 file handler"""
    monkeypatch.setenv("PENSHOT_LOG_TO_FILE", "0")

    config = LoggingConfigManager().to_logging_dict()

    assert "file" not in config["handlers"]
    assert "file" not in config["loggers"][""]["handlers"]
    for logger_config in config["loggers"].values():
        assert "file" not in logger_config["handlers"]


def test_file_logging_enabled_by_default(monkeypatch):
    """未设置开关时保留 file handler"""
    monkeypatch.delenv("PENSHOT_LOG_TO_FILE", raising=False)
    monkeypatch.delenv("PENSHOT_LOG_FILE", raising=False)

    config = LoggingConfigManager().to_logging_dict()

    assert "file" in config["handlers"]
    assert "file" in config["loggers"][""]["handlers"]


def test_file_log_path_can_be_overridden(monkeypatch, tmp_path):
    """PENSHOT_LOG_FILE 覆盖默认文件名，供测试重定向到临时目录"""
    monkeypatch.setenv("PENSHOT_LOG_TO_FILE", "1")
    target = tmp_path / "pytest.log"
    monkeypatch.setenv("PENSHOT_LOG_FILE", str(target))

    handler_config = LoggingConfigManager().get_file_handler_config()

    assert handler_config["filename"] == str(target)