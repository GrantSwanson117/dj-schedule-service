import os, httpx, json, asyncio, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from queryService import QueryService
from eventManager import SSEEventManager, EventModel
from dotenv import load_dotenv

from showRecorder import ShowRecorder

load_dotenv()

tokenURL = os.getenv("TOKEN_URL").strip()
clientID = os.getenv("CLIENT_ID").strip()
clientSecret = os.getenv("CLIENT_SECRET").strip()
authURL = os.getenv("AUTH_URL").strip()
redirectURI = os.getenv("REDIRECT_URI").strip()


class GlobalState:
    activeToken = None
    
state = GlobalState()

#Database service instantiation
db = QueryService('schedule.db')
db.dbFormat()
eventManager = SSEEventManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    trackTask = asyncio.create_task(trackWatchdog())
    showTask = asyncio.create_task(showWatchdog())
    recorderTask = asyncio.create_task(asyncio.to_thread(rc.run))
    yield
    # At shutdown
    trackTask.cancel()
    showTask.cancel()
    recorderTask.cancel()

#Show recorder instantiation
#rc = ShowRecorder(db)

app = FastAPI(lifespan = lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class QuietLogger(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        #Old stubborn URLs. Deprecated.
        msg = record.getMessage()
        return "/spins/get" not in msg and "/spins/update" not in msg and "shows/get" not in msg and "/shows/update"

# 2. Apply it to the uvicorn access logger
logger = logging.getLogger("uvicorn.access")
logger.addFilter(QuietLogger())

async def trackWatchdog():
    prevtrackID = None
    while True:
        try:
            track = await db.dbCurrentTrack()
            
            if track and "id" in track:
                currTrackID = track["id"]
                if currTrackID != prevtrackID:
                    await eventManager.emit(EventModel(
                        type=json.dumps("trackUpdate"),
                        message=json.dumps(f"{track['name']} - {track['artists']}")
                    ))
                    prevtrackID = currTrackID
                    print(f"""New Track: '{track['name']}' - {track['artists']}""")
            
        except Exception as e:
            print(f"Watchdog Error: {e}")
        await asyncio.sleep(10)

async def showWatchdog():
    prevShow = None
    while True:
        try:
            show = db.dbCurrentShow()
            if show:
                currShow = show["show_title"]
                if currShow != prevShow:
                    await eventManager.emit(EventModel(
                        type=json.dumps("showUpdate"),
                        message=json.dumps(f"{show['show_title']} - {show['dj_name']}")
                    ))
                    prevShow = currShow
                    print(f"""New Show: '{show['show_title']}' - {show['dj_name']}""")
                    
        except Exception as e:
            print(f"Watchdog Error: {e}")
        await asyncio.sleep(10)

@app.get("/")
def root(): return {
    "Hello!": "welcome to the KSCU web server! the following endpoints are used for data fetching and monitoring.",
    "/": "root, for help and info",
    "/shows/current": "show currently playing",
    "/stream": "real-time SSE stream for new shows and tracks",
    "/shows/next": "next show scheduled to play (ignoring automated shows)",
    "/tracks/current": "current track playing",
    "/tracks/recent": "returns the 20 most recently played tracks",
}

@app.get("/healthcheck")
def healthCheck(): return {"Server Status:": "OK", "Recorder Status": rc.recorderHealthCheck}

@app.get("/tracks/current/")
@app.get("/tracks/current")
async def currentTrack():
    return await db.dbCurrentTrack()

#Legacy URL
@app.get("/spins/get")
async def currentTrack():
    return await db.dbCurrentTrack()

#Returns 20 most recent tracks
@app.get("/tracks/recent/")
@app.get("/tracks/recent")
async def recentTracks():
    return await db.dbRecentTracks()

@app.get("/shows/current/")
@app.get("/shows/current")
async def currentShow():
    return db.dbCurrentShow()

@app.get("/get-token")
async def get_my_token(code: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            tokenURL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirectURI,
                'client_id': clientID,
                'client_secret': clientSecret,
            }
        )
        return response.json()
    
@app.get("/shows/next/")
@app.get("/shows/next")
def getNextShow():
    return db.dbNextShow()    

@app.get("/stream")
async def streamEvents(request: Request):
    queue = await eventManager.subscribe()

    async def streamGenerator():
        try:
            while True:
                # Check if client is still there
                if await request.is_disconnected(): break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {
                    "event": event.type,
                    "data": event.message
                    }
                except asyncio.TimeoutError:
                    yield ": Empty Request\n\n"
        except Exception as err:
            print(f"Stream error: {err}")
        finally:
            await eventManager.unsubscribe(queue)
            del queue

    return EventSourceResponse(streamGenerator())

@app.post("/emit")
async def newEvent(event: EventModel):
    await eventManager.emit(event)
    return {"message": f"Event '{event.type}' sent to {len(eventManager.subscribers)} listeners"}
