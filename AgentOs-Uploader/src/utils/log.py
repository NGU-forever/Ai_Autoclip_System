"""Uploader 日志模块，使用 print 避免依赖 loguru"""
import sys


def _log(level: str, msg: str):
    print(f"[{level}] {msg}", file=sys.stderr)


class _SimpleLogger:
    def info(self, msg: str):
        _log("INFO", msg)

    def success(self, msg: str):
        _log("SUCCESS", msg)

    def error(self, msg: str):
        _log("ERROR", msg)

    def warning(self, msg: str):
        _log("WARNING", msg)

    def debug(self, msg: str):
        _log("DEBUG", msg)

    def exception(self, msg: str):
        _log("EXCEPTION", msg)


douyin_logger = _SimpleLogger()
tencent_logger = _SimpleLogger()
xiaohongshu_logger = _SimpleLogger()
