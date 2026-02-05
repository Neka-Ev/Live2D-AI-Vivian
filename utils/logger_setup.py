import logging
import sys

class ColoredFormatter(logging.Formatter):
    """
    自定义日志格式化器，支持根据日志级别输出不同颜色的日志信息。
    """
    # ANSI 颜色代码
    GREY = "\x1b[38;21m"
    GREEN = "\x1b[32;21m"
    YELLOW = "\x1b[33;21m"
    RED = "\x1b[31;21m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    # 日志格式
    fmt = "[%(levelname)s] %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + fmt + RESET,
        logging.INFO: GREEN + fmt + RESET,      # INFO 显示为绿色
        logging.WARNING: YELLOW + fmt + RESET,
        logging.ERROR: RED + fmt + RESET,       # ERROR 显示为红色
        logging.CRITICAL: BOLD_RED + fmt + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def get_logger(name: str) -> logging.Logger:
    """
    获取一个配置好颜色输出、且防止重复打印的 Logger 实例。
    """
    logger = logging.getLogger(name)

    # 防止日志向上传播给 Root Logger 导致重复
    logger.propagate = False

    # 仅当 logger 还没有 Handler 时才添加，防止多次调用导致重复输出
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # 创建流处理器（输出到控制台）
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColoredFormatter())

        logger.addHandler(handler)

    return logger
