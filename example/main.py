
from xdeek_logger import MyLogger

if __name__ == '__main__':
    import time
    import json
    import asyncio

    # 初始化日志记录器
    # 替换为真实的远程日志收集URL，或者设置为 None
    remote_log_url = "https://your-logging-endpoint.com/logs"
    # log = MyLogger("test_log", remote_log_url=remote_log_url)
    log = MyLogger("test_log")


    @log.log_decorator("快看, 异常了, 别唧唧哇哇, 快排查")
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
        log.info("test...")


