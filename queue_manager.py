"""绘图请求队列管理。"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Optional

QueueItem = dict
QueueHandler = Callable[[QueueItem], Awaitable[None]]
ErrorHandler = Callable[[Exception, QueueItem], Awaitable[None]]


class RequestQueue:
    """按顺序处理绘图请求，自动加入延迟。"""

    def __init__(
        self,
        handler: QueueHandler,
        *,
        min_delay: float = 3.0,
        max_delay: float = 5.0,
        error_handler: Optional[ErrorHandler] = None,
    ) -> None:
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("延迟范围配置无效")
        self.queue: asyncio.Queue[Optional[QueueItem]] = asyncio.Queue()
        self.handler = handler
        self.error_handler = error_handler
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._worker(), name="novelai-request-queue")

    async def stop(self) -> None:
        if not self._task:
            return
        self._running = False
        await self.queue.put(None)
        await self._task
        self._task = None

    async def enqueue(self, item: QueueItem) -> None:
        await self.queue.put(item)

    async def _worker(self) -> None:
        while self._running:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            try:
                await self.handler(item)
            except Exception as exc:  # noqa: BLE001
                if self.error_handler:
                    await self.error_handler(exc, item)
            finally:
                self.queue.task_done()

            if not self.queue.empty():
                await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        # 清空剩余的哨兵值
        while not self.queue.empty():
            item = await self.queue.get()
            self.queue.task_done()
            if item is None:
                break
