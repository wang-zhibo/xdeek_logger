## Enhanced Logger

这是一个基于 [Loguru](https://github.com/Delgan/loguru) 的扩展日志记录器，提供了一系列增强特性，包括：

- 自定义日志格式  
- 日志轮转和保留策略  
- 上下文信息管理（如 `request_id`）  
- 远程日志收集（使用线程池防止阻塞）  
- 装饰器用于记录函数调用和执行时间，支持同步/异步函数  
- 自定义日志级别（避免与 Loguru 预定义的冲突）  
- 统一异常处理  

---

### 功能概述

1. **自定义日志格式**  
   可自由配置字段，如时间、进程/线程 ID、日志级别、请求 ID、所在文件、函数、行号等。

2. **日志轮转与保留**  
   - 支持按照文件大小、时间或文件数量进行滚动，并可自动删除过期日志。  
   - 默认使用大小轮转：单个文件超过 `max_size` MB 时自动滚动。  
   - 默认保留策略 `retention='9 days'`，可根据需要自定义。

3. **上下文管理**  
   - 使用 `ContextVar` 储存 `request_id`，可在异步环境中区分不同请求来源的日志。

4. **远程日志收集**  
   - 通过自定义处理器，使用线程池的方式将日志上报到远程服务，避免主线程阻塞。  
   - 默认仅收集 `ERROR` 及以上等级的日志。可在 `_configure_remote_logging()` 方法中自行配置。

5. **装饰器**  
   - `log_decorator` 可装饰任意同步或异步函数，自动记录：
     - 函数调用开始  
     - 参数、返回值  
     - 函数执行耗时  
     - 异常信息（可选择是否抛出异常）

6. **自定义日志级别**  
   - 通过 `add_custom_level` 方法添加额外的日志级别（如 `AUDIT`, `SECURITY` 等），避免与已有日志级别冲突。

7. **统一异常处理**  
   - 注册全局异常处理 (`sys.excepthook`)，捕获任何未处理的异常并记录。

---

### 目录结构

. ├── logs/ # 日志存放目录（默认） ├── my_logger.py # MyLogger 类源码 ├── README.md # 使用说明 └── requirements.txt # Python依赖（如有）

yaml
复制代码

> 其中 `logs/` 是默认日志目录，可以通过初始化时的 `log_dir` 参数修改。

---


### 安装

```bash
pip install xdeek-logger
```


### 使用示例
    example/main.py


### 导入并使用

```
from xdeek_logger import MyLogger

"""
初始化日志记录器
可自定义:
  - 主日志文件名 (e.g., "app_log")
  - 日志目录 log_dir (默认 "logs")
  - 单个日志文件体积最大值 max_size (MB)
  - 日志保留策略 retention (e.g., "7 days")
  - 远程日志收集地址 remote_log_url (默认 None)
  - 线程池最大工作线程数 max_workers (默认 5)
"""
logger = MyLogger(
    file_name="app_log",
    log_dir="logs",
    max_size=50,
    retention="7 days",
    remote_log_url=None,
    max_workers=5
)

```

### 调用日志方法

```
"""直接使用 Loguru 的常见日志方法"""
logger.info("This is an info message.")
logger.debug("Debug details here.")
logger.warning("Be cautious!")
logger.error("An error occurred.")
logger.critical("Critical issue!")
logger.trace("This is a trace message - only if Loguru TRACE level is enabled.")

logger.log("CUSTOM_LEVEL", "A special custom message.")

```

### 使用装饰器记录函数调用

```
@logger.log_decorator("A division error occurred.")
def divide(a, b):
    return a / b

try:
    result = divide(10, 0)  
    """# 将触发 ZeroDivisionError"""
except ZeroDivisionError:
    logger.exception("Handled ZeroDivisionError.")

```
- 此装饰器会自动在函数开始和结束时分别记录函数名、参数、返回值以及耗时。
- 如果出现异常，则记录 traceback 并打印自定义提示信息。


### 记录异步函数调用

```
import asyncio

@logger.log_decorator("Async function error.")
async def async_task():
    await asyncio.sleep(1)
    return "Async result"

async def main():
    result = await async_task()
    logger.info(f"Result: {result}")

asyncio.run(main())

```

### 设置和重置 request_id

```
"""# 设置某个上下文的 request_id"""
token = logger.request_id_var.set("12345")

"""# ...执行与你的请求相关的操作，所有日志都带上 request_id=12345"""

"""# 结束后重置"""
logger.request_id_var.reset(token)

``` 


### 远程日志收集

- 在初始化 MyLogger 时，指定 remote_log_url 即可启用远程日志上报功能：

```
logger = MyLogger(
    file_name="app_log",
    remote_log_url="https://your-logging-endpoint.com/logs"
)

``` 





### 常见问题

#### 1. 如何关闭日志多文件策略？
- 如果仅需要一个主日志文件，可去掉或注释掉 `_get_level_log_path()` 相关的 `logger.add(...)` 调用。
- 如果希望“只按级别分文件、不需要主日志文件”，可以删除对应的添加主日志文件的 `add` 调用。

#### 2. 如何自定义轮转策略（按天、按小时等）？
- 将 `rotation=f"{self.max_size} MB"` 改为 `rotation="1 day"`、`rotation="00:00"` 等，即可使用 Loguru 的时间轮转功能。

#### 3. 如何自定义日志输出格式？
- 修改 `custom_format` 变量，或在 `logger.add()` 中使用你喜欢的格式，如 **JSON** 格式、单行简洁格式等。

#### 4. 如何在函数装饰器中抛出异常？
- 在装饰器里捕获异常后，如果希望装饰器内不“吞掉”异常，可在 `except` 块里添加 `raise`，这样异常会继续向上传递。

#### 5. 如何在远程收集中添加鉴权信息？
- 在 `_send_to_remote` 方法里，可在 `headers` 中添加 `Authorization` token 或其他自定义请求头。

