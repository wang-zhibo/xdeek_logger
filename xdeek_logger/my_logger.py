#!/usr/bin/env python
# -*- coding:utf-8 -*-

# Author: zhibo.wang
# E-mail: gm.zhibo.wang@gmail.com
# Date  : 2025-01-03
# Desc  : Enhanced Logger with Loguru (with async support) + Language Option

import os
import sys
import inspect
import requests
import traceback

from functools import wraps
from time import perf_counter
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor

from loguru import logger


class MyLogger:
    """
    基于 Loguru 的增强日志记录器，具有以下功能：
    - 自定义日志格式
    - 日志轮转和保留策略
    - 上下文信息管理（如 request_id）
    - 远程日志收集（使用线程池防止阻塞）
    - 装饰器用于记录函数调用和执行时间，支持同步/异步函数
    - 自定义日志级别（避免与 Loguru 预定义的冲突）
    - 统一异常处理

    新增：
    - 可指定语言（中文/英文），默认中文
    """

    # 在此定义常用提示语的多语言版本
    _LANG_MAP = {
        'zh': {
            'UNHANDLED_EXCEPTION': "未处理的异常",
            'START_FUNCTION_CALL': "----------- 开始函数调用 -----------",
            'END_FUNCTION_CALL': "----------- 结束函数调用 -----------",
            'START_ASYNC_FUNCTION_CALL': "----------- 开始异步函数调用 -----------",
            'END_ASYNC_FUNCTION_CALL': "----------- 结束异步函数调用 -----------",
            'CALLING_FUNCTION': '调用函数 "{func}"，参数: args={args}; kwargs={kwargs}',
            'CALLING_ASYNC_FUNCTION': '调用异步函数 "{func}"，参数: args={args}; kwargs={kwargs}',
            'FUNCTION_RETURNED': '函数 "{func}" 返回: {result} (耗时: {duration:.4f}s)',
            'ASYNC_FUNCTION_RETURNED': '异步函数 "{func}" 返回: {result} (耗时: {duration:.4f}s)',
            'FAILED_REMOTE': "发送日志到远程服务器失败: {error}",
        },
        'en': {
            'UNHANDLED_EXCEPTION': "Unhandled exception",
            'START_FUNCTION_CALL': "----------- Start Function Call -----------",
            'END_FUNCTION_CALL': "----------- End Function Call -----------",
            'START_ASYNC_FUNCTION_CALL': "----------- Start Async Function Call -----------",
            'END_ASYNC_FUNCTION_CALL': "----------- End Async Function Call -----------",
            'CALLING_FUNCTION': 'Calling function "{func}" with args={args}; kwargs={kwargs}',
            'CALLING_ASYNC_FUNCTION': 'Calling async function "{func}" with args={args}; kwargs={kwargs}',
            'FUNCTION_RETURNED': 'Function "{func}" returned: {result} (Duration: {duration:.4f}s)',
            'ASYNC_FUNCTION_RETURNED': 'Async function "{func}" returned: {result} (Duration: {duration:.4f}s)',
            'FAILED_REMOTE': "Failed to send log to remote server: {error}",
        }
    }

    def __init__(
        self,
        file_name,
        log_dir='logs',
        max_size=14,        # 单位：MB
        retention='7 days',
        remote_log_url=None,
        max_workers=3,
        work_type=False,
        language='zh'       # 新增：语言选项，默认为中文
    ):
        """
        初始化日志记录器。

        Args:
            file_name (str): 日志文件名称（主日志文件前缀）。
            log_dir (str): 日志文件目录。
            max_size (int): 日志文件大小（MB）超过时进行轮转。
            retention (str): 日志保留策略。
            remote_log_url (str, optional): 远程日志收集的URL。如果提供，将启用远程日志收集。
            max_workers (int): 线程池的最大工作线程数。
            work_type (bool): False 测试环境
            language (str): 'zh' 或 'en'，表示日志输出语言，默认为中文。
        """
        self.file_name = file_name
        self.log_dir = log_dir
        self.max_size = max_size
        self.retention = retention
        self.remote_log_url = remote_log_url

        # 语言选项
        self.language = language if language in ('zh', 'en') else 'zh'

        # 定义上下文变量，用于存储 request_id
        self.request_id_var = ContextVar("request_id", default="no-request-id")

        # 使用 patch 确保每条日志记录都包含 'request_id'
        self.logger = logger.patch(
            lambda record: record["extra"].update(
                request_id=self.request_id_var.get() or "no-request-id"
            )
        )
        if work_type:
            self.enqueue = False
            self.diagnose = False
            self.backtrace = False
        else:
            self.enqueue = True
            self.diagnose = True
            self.backtrace = True

        # 用于远程日志发送的线程池
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 初始化 Logger 配置
        self.configure_logger()

    def _msg(self, key, **kwargs):
        """
        根据当前语言，从 _LANG_MAP 中获取对应文本。
        可使用 kwargs 替换字符串中的占位符。
        """
        text = self._LANG_MAP[self.language].get(key, "")
        return text.format(**kwargs)

    def configure_logger(self):
        """
        配置 Loguru 日志记录器：控制台输出、文件输出、远程日志收集、自定义日志级别。
        """
        # 移除所有现有的处理器，重新添加
        self.logger.remove()

        # 定义日志格式：可根据需要自由增减字段
        # 包含时间、进程 ID、线程 ID、日志级别、request_id、调用位置等
        # 目前去除进程 ID、线程 ID
        """
        custom_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<cyan>PID:{process}</cyan>/<cyan>TID:{thread}</cyan> | "
            "<level>{level: <8}</level> | "
            "ReqID:{extra[request_id]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        """
        custom_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "ReqID:{extra[request_id]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )

        # 添加控制台处理器
        self.logger.add(
            sys.stdout,
            format=custom_format,
            level="DEBUG",      # 控制台一般是 DEBUG 或更高
            enqueue=True,
        )

        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)

        # 添加一个主日志文件（带轮转和保留策略），记录所有级别日志
        self.logger.add(
            os.path.join(self.log_dir, f"{self.file_name}.log"),
            format=custom_format,
            level="DEBUG",
            rotation=f"{self.max_size} MB",
            retention=self.retention,
            compression="zip",
            encoding='utf-8',
            enqueue=True,
            diagnose=True,
            backtrace=True,
        )

        # 仅示例演示：为 ERROR 级别单独输出到文件
        self.logger.add(
            self._get_level_log_path("error"),
            format=custom_format,
            level="ERROR",
            rotation=f"{self.max_size} MB",
            retention=self.retention,
            compression="zip",
            encoding='utf-8',
            enqueue=self.enqueue,
            diagnose=self.diagnose,
            backtrace=self.backtrace,
        )

        # 远程日志收集
        if self.remote_log_url:
            self._configure_remote_logging()

        # 设置统一异常处理
        self.setup_exception_handler()

    def _configure_remote_logging(self):
        """
        配置远程日志收集。
        """
        # 当远程日志收集启用时，只发送 ERROR 及以上级别的日志
        self.logger.add(
            self.remote_sink,
            level="ERROR",
            enqueue=self.enqueue,
        )

    def setup_exception_handler(self):
        """
        设置统一的异常处理函数，将未处理的异常记录到日志。
        """
        def exception_handler(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                # 允许程序被 Ctrl+C 中断
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            self.logger.opt(exception=True).error(
                self._msg('UNHANDLED_EXCEPTION'),
                exc_info=(exc_type, exc_value, exc_traceback)
            )

        sys.excepthook = exception_handler

    def _get_level_log_path(self, level_name):
        """
        获取不同级别日志文件的路径。
        """
        return os.path.join(self.log_dir, f"{self.file_name}_{level_name}.log")

    def get_log_path(self, message):
        """
        如果需要将所有日志按照级别分文件时，可使用此方法。
        """
        log_level = message.record["level"].name.lower()
        log_file = f"{log_level}.log"
        return os.path.join(self.log_dir, log_file)

    def remote_sink(self, message):
        """
        自定义的远程日志处理器，将日志发送到远程服务器（使用线程池防止阻塞）。
        """
        self._executor.submit(self._send_to_remote, message)

    def _send_to_remote(self, message):
        """
        线程池中实际执行的远程日志发送逻辑。
        """
        log_entry = message.record
        payload = {
            "time": log_entry["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "level": log_entry["level"].name,
            "message": log_entry["message"],
            "file": os.path.basename(log_entry["file"].path) if log_entry["file"] else "",
            "line": log_entry["line"],
            "function": log_entry["function"],
            "request_id": log_entry["extra"].get("request_id", "no-request-id")
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                self.remote_log_url,
                headers=headers,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
        except requests.RequestException as e:
            # 如果无法发送到远程服务器，仅做警告记录
            self.logger.warning(self._msg('FAILED_REMOTE', error=e))

    def add_custom_level(self, level_name, no, color, icon):
        """
        增加自定义日志级别。

        Args:
            level_name (str): 日志级别名称。
            no (int): 日志级别编号。
            color (str): 日志级别颜色。
            icon (str): 日志级别图标。
        """
        try:
            self.logger.level(level_name, no=no, color=color, icon=icon)
            self.logger.debug(f"Custom log level '{level_name}' added.")
        except TypeError:
            # 如果日志级别已存在，记录调试信息
            self.logger.debug(f"Log level '{level_name}' already exists, skipping.")

    def __getattr__(self, level: str):
        """
        使 MyLogger 支持直接调用 Loguru 的日志级别方法。

        Args:
            level (str): 日志级别方法名称。
        """
        return getattr(self.logger, level)

    def log_decorator(self, msg="快看, 异常了, 别唧唧哇哇, 快排查!"):
        """
        日志装饰器，自动判断被装饰函数是同步还是异步，
        记录函数名称、参数、返回值、运行时间和异常信息。

        Args:
            msg (str): 发生异常时记录的自定义提示信息（此处保留原用法，不做多语言处理）。
        """

        def decorator(func):
            if inspect.iscoroutinefunction(func):
                # 异步函数
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    self._log_start(func.__name__, args, kwargs, is_async=True)
                    start_time = perf_counter()
                    try:
                        result = await func(*args, **kwargs)
                        duration = perf_counter() - start_time
                        self._log_end(func.__name__, result, duration, is_async=True)
                        return result
                    except Exception:
                        self.logger.exception(f'Async function "{func.__name__}": {msg}')
                        self.logger.info(self._msg('END_ASYNC_FUNCTION_CALL'))
                        # 如果想在装饰器内抑制异常，可不再抛出
                        # raise
                return async_wrapper
            else:
                # 同步函数
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    self._log_start(func.__name__, args, kwargs, is_async=False)
                    start_time = perf_counter()
                    try:
                        result = func(*args, **kwargs)
                        duration = perf_counter() - start_time
                        self._log_end(func.__name__, result, duration, is_async=False)
                        return result
                    except Exception:
                        self.logger.exception(f'Function "{func.__name__}": {msg}')
                        self.logger.info(self._msg('END_FUNCTION_CALL'))
                        # 如果想在装饰器内抑制异常，可不再抛出
                        # raise
                return sync_wrapper
        return decorator

    def _log_start(self, func_name, args, kwargs, is_async=False):
        """
        记录函数调用开始的公共逻辑。
        """
        if is_async:
            self.logger.info(self._msg('START_ASYNC_FUNCTION_CALL'))
            self.logger.info(
                self._msg('CALLING_ASYNC_FUNCTION', func=func_name, args=args, kwargs=kwargs)
            )
        else:
            self.logger.info(self._msg('START_FUNCTION_CALL'))
            self.logger.info(
                self._msg('CALLING_FUNCTION', func=func_name, args=args, kwargs=kwargs)
            )

    def _log_end(self, func_name, result, duration, is_async=False):
        """
        记录函数调用结束的公共逻辑。
        """
        if is_async:
            self.logger.info(
                self._msg('ASYNC_FUNCTION_RETURNED', func=func_name, result=result, duration=duration)
            )
            self.logger.info(self._msg('END_ASYNC_FUNCTION_CALL'))
        else:
            self.logger.info(
                self._msg('FUNCTION_RETURNED', func=func_name, result=result, duration=duration)
            )
            self.logger.info(self._msg('END_FUNCTION_CALL'))


# """
# ==========================
# 以下为使用示例
# ==========================
if __name__ == '__main__':
    import time
    import json
    import asyncio

    # 初始化日志记录器
    # - language='zh' 输出中文
    # - language='en' 输出英文
    remote_log_url = None  # "https://your-logging-endpoint.com/logs"
    log = MyLogger("test_log", remote_log_url=remote_log_url, language='zh')

    @log.log_decorator("ZeroDivisionError occurred.")
    def test_zero_division_error(a, b):
        return a / b

    @log.log_decorator("JSONDecodeError occurred.")
    def test_error():
        json.loads("asdasd")

    @log.log_decorator("Function execution took too long.")
    def compute_something_sync():
        time.sleep(1)
        return "Sync computation completed"

    @log.log_decorator("Async function execution took too long.")
    async def compute_something_async():
        await asyncio.sleep(1)
        return "Async computation completed"

    # 设置 request_id
    token = log.request_id_var.set("12345")

    try:
        # 常见日志级别示例
        log.info('This is an info log.')
        log.debug('This is a debug log.')
        log.warning('This is a warning log.')
        log.error('This is an error log.')
        log.critical('This is a critical log.')
        log.trace('This is a TRACE level log (Loguru default).')

        # 测试同步函数
        try:
            result = test_zero_division_error(1, 0)
            log.info(f"test_zero_division_error result: {result}")
        except ZeroDivisionError:
            log.exception("Caught a ZeroDivisionError.")
        result = test_zero_division_error(1, 1)

        # 测试另一个示例函数
        try:
            result = test_error()
        except json.JSONDecodeError:
            log.exception("Caught a JSONDecodeError.")

        # 测试同步函数
        result = compute_something_sync()
        log.info(f"compute_something_sync result: {result}")

        # 测试异步函数
        async def main():
            result = await compute_something_async()
            log.info(f"compute_something_async result: {result}")

        asyncio.run(main())

    finally:
        # 重置 request_id
        log.request_id_var.reset(token)
        log.info("All done.")
# """
