
from xdeek_logger import MyLogger

if __name__ == '__main__':
    import time
    import json
    import asyncio
    import random

    # 自定义日志格式
    custom_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "ReqID:{extra[request_id]} | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<magenta>{process}</magenta> - "
        "<level>{message}</level>"
    )

    # 初始化日志记录器，使用新功能
    log = MyLogger(
        "test_log",
        rotation_time="1 day",           # 每天轮转
        custom_format=custom_format,     # 自定义格式
        filter_level="DEBUG",            # 日志级别
        compression="zip",               # 压缩格式
        file_pattern="{time:YYYY-MM-DD}", # 文件命名模式
        enable_stats=True,               # 启用统计
        categories=["api", "db", "ui"]   # 日志分类
    )

    # 添加自定义日志级别
    log.add_custom_level("IMPORTANT", no=25, color="<yellow>", icon="⚠️")

    @log.log_decorator("除零错误", level="ERROR")
    def test_zero_division_error(a, b):
        return a / b

    @log.log_decorator("JSON解析错误", level="WARNING")
    def test_error():
        json.loads("invalid_json")

    @log.log_decorator("耗时操作", level="INFO", trace=False)
    def compute_something_sync():
        time.sleep(1)
        return "同步计算完成"

    @log.log_decorator("异步耗时操作")
    async def compute_something_async():
        await asyncio.sleep(1)
        return "异步计算完成"

    @log.log_decorator("生成随机数", level="INFO", trace=False)
    def generate_random_number(min_val=1, max_val=100):
        return random.randint(min_val, max_val)

    # 设置请求ID
    token = log.request_id_var.set("REQ-12345")

    try:
        # 基本日志测试
        log.info('这是一条信息日志')
        log.debug('这是一条调试日志')
        log.warning('这是一条警告日志')
        log.error('这是一条错误日志')
        log.critical('这是一条严重错误日志')
        
        # 使用自定义日志级别
        log.log("IMPORTANT", "这是一条重要日志消息")
        
        # 使用标签功能
        log.log_with_tag("INFO", "这是带标签的日志", "FEATURE")
        log.log_with_tag("WARNING", "这是带标签的警告", "DEPRECATED")
        
        # 使用分类功能
        log.log_with_category("INFO", "数据库连接成功", "db")
        log.log_with_category("ERROR", "API请求失败", "api")
        log.log_with_category("DEBUG", "UI组件渲染", "ui")

        # 测试异常处理
        try:
            result = test_zero_division_error(1, 0)
        except ZeroDivisionError:
            log.exception("捕获到除零错误")

        try:
            result = test_error()
        except json.JSONDecodeError:
            log.exception("捕获到JSON解析错误")

        # 测试同步函数
        result = compute_something_sync()
        log.info(f"同步计算结果: {result}")
        
        # 测试随机数生成
        for _ in range(3):
            num = generate_random_number(1, 1000)
            log.info(f"生成的随机数: {num}")

        # 测试异步函数
        async def main():
            # 单个异步任务
            result = await compute_something_async()
            log.info(f"异步计算结果: {result}")
            
            # 多个并发异步任务
            tasks = [compute_something_async() for _ in range(3)]
            results = await asyncio.gather(*tasks)
            log.info(f"多任务异步结果: {results}")

        asyncio.run(main())
        
        # 输出日志统计
        print("\n" + log.get_stats())

    finally:
        # 重置请求ID
        log.request_id_var.reset(token)
        log.info("测试完成")


