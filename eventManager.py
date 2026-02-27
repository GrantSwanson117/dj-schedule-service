import asyncio, json
from pydantic import BaseModel

class EventModel(BaseModel):
    type: str
    message: str

class SSEEventManager:
    def __init__(self):
        self.subscribers = set()

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=10)
        self.subscribers.add(queue)
        print(f"New subscriber. Total: {len(self.subscribers)}")
        return queue
    
    async def unsubscribe(self, queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            print(f"Lost subscriber. Total: {len(self.subscribers)}")

    async def emit(self, event: EventModel):
        if not self.subscribers: return
        for queue in self.subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
            #Drop oldest event in queue
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except:
                    pass

    async def event_generator(self):
        counter = 0
        while True:
            data = {"message": f"Ping {counter}"}
            yield f"data: {json.dumps(data)}\n\n"
            counter += 1
            await asyncio.sleep(10)
