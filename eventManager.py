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
        queue = asyncio.Queue(maxsize=15)
        self.subscribers.add(queue)
        print(f"SYSTEM: Viewer Count: {len(self.subscribers)}")
        return queue
    
    async def unsubscribe(self, queue):
        self.subscribers.discard(queue)
        print(f"SYSTEM: Viewer Count: {len(self.subscribers)}")

    async def emit(self, event: EventModel):
        if not self.subscribers: 
            return

        payload = {
            "event": event.type,
            "data": event.message
        }
        currentViewers = list(self.subscribers)

        for queue in currentViewers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:

                self.subscribers.discard(queue)
            except Exception:
                self.subscribers.discard(queue)
        await asyncio.sleep(0)