#!/usr/bin/env python
# -*- coding:utf-8 -*-

# Author: zhibo.wang
# E-mail: gm.zhibo.wang@gmail.com
# Date  : 2025-01-03
# Desc  : Enhanced Logger with Loguru (with async support)

import os
import sys
import inspect
import requests
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
    """

    def __init__(
        self,
        file_name,
        log_dir='logs',
        max_size=36,
        retention='9 days',
        remote_log_url=None,
        max_workers=5,
    ):
        """
        初始化日志记录器。

        Args:
            file_name (str): 日志文件名称。
            log_dir (str): 日志文件目录。
            max_size (int): 日志文件大小（MB）超过时进行轮转。
            retention (str): 日志保留策略。
            remote_log_url (str, optional): 远程日志收集的URL。如果提供，将启用远程日志收集。
            max_workers (int): 线程池的最大工作线程数。
        """
        self.file_name = file_name
        self.log_dir = log_dir
        self.max_size = max_size
        self.retention = retention
        self.remote_log_url = remote_log_url

        # 定义上下文变量，用于存储 request_id
        self.request_id_var = ContextVar("request_id", default="unknown")

        # 使用 patch 确保每条日志记录都包含 'request_id'
        self.logger = logger.patch(
            lambda record: record["extra"].update(request_id=self.request_id_var.get())
        )

        # 用于远程日志发送的线程池
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 初始化 Logger 配置
        self.configure_logger()

    def configure_logger(self):
        """
        配置 Loguru 日志记录器：控制台输出、文件输出、远程日志收集、自定义日志级别。
        """
        # 移除所有现有的处理器
        self.logger.remove()

        # 定义日志格式
        custom_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "RequestID:{extra[request_id]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )

        # 添加控制台处理器
        self.logger.add(
            sys.stdout,
            format=custom_format,
            level="DEBUG",
            enqueue=True,
        )

        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)

        # 添加文件处理器（带轮转和保留策略）
        self.logger.add(
            os.path.join(self.log_dir, f"{self.file_name}.log"),
            format=custom_format,
            level="DEBUG",
            rotation=f"{self.max_size} MB",
            retention=self.retention,
            compression="zip",
            encoding='utf-8',
            diagnose=True,
            colorize=True,
            backtrace=True,
        )

        # 根据日志级别动态生成文件名
        self.logger.add(
            self.get_log_path,
            format=custom_format,
            level="DEBUG",
            enqueue=True
        )

        # 如果提供了远程日志收集URL，添加远程日志处理器
        if self.remote_log_url:
            self.logger.add(
                self.remote_sink,
                level="ERROR",
                enqueue=True
            )

        # 添加自定义日志级别（避免与 Loguru 预定义的冲突）
        self.add_custom_level("CUSTOM_LEVEL", no=15, color="<magenta>", icon="🌟")

        # 设置统一异常处理
        self.setup_exception_handler()

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
                "未处理的异常",
                exc_info=(exc_type, exc_value, exc_traceback)
            )

        sys.excepthook = exception_handler

    def get_log_path(self, message):
        """
        根据日志级别返回日志文件路径。

        Args:
            message: Loguru 日志消息对象。

        Returns:
            str: 日志文件路径。
        """
        log_level = message.record["level"].name.lower()
        log_file = f"{log_level}.log"
        return os.path.join(self.log_dir, log_file)

    def remote_sink(self, message):
        """
        自定义的远程日志处理器，将日志发送到远程服务器（使用线程池防止阻塞）。
        """
        # 在线程池中发送日志
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
            "file": os.path.basename(log_entry["file"].path),
            "line": log_entry["line"],
            "function": log_entry["function"],
            "request_id": log_entry["extra"].get("request_id", "unknown")
        }
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(
                self.remote_log_url,
                headers=headers,
                json=payload,
                timeout=6
            )
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.warning(f"Failed to send log to remote server: {e}")

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

        Returns:
            method: 对应的 Loguru 日志方法。
        """
        return getattr(self.logger, level)

    def log_decorator(self, msg="An exception occurred. Please check the logs."):
        """
        日志装饰器，自动判断被装饰函数是同步还是异步，
        记录函数的名称、参数、返回值、运行时间和异常信息。

        Args:
            msg (str): 异常信息模板。

        Returns:
            function: 装饰器函数。
        """

        def decorator(func):
            if inspect.iscoroutinefunction(func):
                # 异步函数
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    self.logger.info('----------- Start Async Function Call -----------')
                    self.logger.info(f'Calling async function "{func.__name__}" with args: {args}; kwargs: {kwargs}')
                    start_time = perf_counter()
                    try:
                        result = await func(*args, **kwargs)
                        duration = perf_counter() - start_time
                        self.logger.info(
                            f'Async function "{func.__name__}" returned: {result} '
                            f'(Duration: {duration:.4f}s)'
                        )
                        self.logger.info('----------- End Async Function Call -----------')
                        return result
                    except Exception:
                        self.logger.exception(f'Async function "{func.__name__}": {msg}')
                        self.logger.info('----------- End Async Function Call -----------')
                        # 可选择是否重新抛出异常
                        # raise

                return async_wrapper
            else:
                # 同步函数
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    self.logger.info('----------- Start Function Call -----------')
                    self.logger.info(f'Calling function "{func.__name__}" with args: {args}; kwargs: {kwargs}')
                    start_time = perf_counter()
                    try:
                        result = func(*args, **kwargs)
                        duration = perf_counter() - start_time
                        self.logger.info(
                            f'Function "{func.__name__}" returned: {result} '
                            f'(Duration: {duration:.4f}s)'
                        )
                        self.logger.info('----------- End Function Call -----------')
                        return result
                    except Exception:
                        self.logger.exception(f'Function "{func.__name__}": {msg}')
                        self.logger.info('----------- End Function Call -----------')
                        # 可选择是否重新抛出异常
                        # raise

                return sync_wrapper

        return decorator



"""
# ==========================
# 以下为使用示例
# ==========================
if __name__ == '__main__':
    import time
    import json
    import asyncio

    # 初始化日志记录器
    # 替换为真实的远程日志收集URL，或者设置为 None
    remote_log_url = "https://your-logging-endpoint.com/logs"
    log = MyLogger("test_log", remote_log_url=remote_log_url)

    # 增加自定义日志级别
    log.add_custom_level("CUSTOM_LEVEL", no=15, color="<magenta>", icon="🌟")

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
        # 日志示例
        log.info('This is an info log.')
        log.debug('This is a debug log.')
        log.warning('This is a warning log.')
        log.error('This is an error log.')
        log.critical('This is a critical log.')
        log.trace('This is a TRACE level log.')  # Loguru预定义的TRACE级别

        # 测试同步函数
        try:
            result = test_zero_division_error(1, 0)
            log.info(f"test_zero_division_error result: {result}")
        except ZeroDivisionError:
            log.exception("Caught a ZeroDivisionError.")

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

"""



