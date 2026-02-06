import asyncio
from pydantic import BaseModel
import httpx
import json

class EventModel(BaseModel):
    type: str
    message: str

class SSEEventManager:
    def __init__(self):
        self.subscribers = set()

    async def subscribe(self):
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue
    
    async def unsubscribe(self, queue):
        self.subscribers.discard(queue)

    async def emit(self, event: EventModel):
        if not self.subscribers: return
        for queue in self.subscribers:
            await queue.put(event) 
    

    async def event_generator(self):
        counter = 0
        while True:
            data = {"message": f"Ping {counter}"}
            yield f"data: {json.dumps(data)}\n\n"
            counter += 1
            await asyncio.sleep(10)
