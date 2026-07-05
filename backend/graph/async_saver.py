import asyncio
from langgraph.checkpoint.postgres import PostgresSaver


class AsyncPostgresSaver(PostgresSaver):
    """异步包装器，将同步 PostgresSaver 的方法转为 asyncio.to_thread 调用"""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id)

    async def aget_writes(self, config):
        return await asyncio.to_thread(self.get_writes, config)

    async def alist(self, config, filter=None, before=None, limit=None):
        return await asyncio.to_thread(self.list, config, filter=filter, before=before, limit=limit)