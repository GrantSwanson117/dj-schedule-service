import asyncio
from pydantic import BaseModel

class EventModel(BaseModel):
    type: str
    message: str

class SSEEventManager:
    def __init__(self):
        self.subscribers = set()

    def subscribe(self):
        queue = asyncio.Queue
        self.subscribers.add(queue)
        return queue
    
    def unsubscribe(self, queue):
        self.subscribers.remove(queue)

    async def emit(self, event: EventModel):
        if not self.subscribers: return
        for queue in self.subscribers:
            await queue.put(event) 