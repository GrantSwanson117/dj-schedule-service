import asyncio
import json
import weakref
from pydantic import BaseModel

class EventModel(BaseModel):
    type: str
    message: str

class SSEEventManager:
    def __init__(self):
        self.subscribers = weakref.WeakSet()

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=15) # Slightly larger buffer
        self.subscribers.add(queue)
        print(f"New subscriber. Total: {len(self.subscribers)}")
        return queue
    
    async def unsubscribe(self, queue):
        self.subscribers.discard(queue)
        print(f"Subscriber removed. Total: {len(self.subscribers)}")

    async def emit(self, event: EventModel):
        if not self.subscribers: 
            return

        payload = {
            "event": event.type,
            "data": event.message
        }

        for queue in list(self.subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait() # Pop the oldest
                    queue.put_nowait(payload)
                except asyncio.QueueEmpty:
                    pass