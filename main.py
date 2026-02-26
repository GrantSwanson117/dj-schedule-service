import os
import httpx
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
from fastapi.responses import RedirectResponse
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

#Show recorder instantiation
rc = ShowRecorder(db)

app = FastAPI(lifespan = lifespan, redirect_slashes= False)

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:1313",
    "https://kscu.org/"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

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

'''@app.middleware("http")
async def silence_legacy_spins(request: Request, call_next):
    if request.url.path == "/spins/get" or "/spins/update":
        return RedirectResponse(url="/tracks/current", status_code=307)
    
    response = await call_next(request)
    return response'''

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

@app.get("/tracks/current")
async def currentTrack():
    return await db.dbCurrentTrack()

#Legacy URL
@app.get("/spins/get")
async def currentTrack():
    return await db.dbCurrentTrack()

#Returns 20 most recent tracks
@app.get("/tracks/recent")
async def recentTracks():
    return await db.dbRecentTracks()

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
                
                event = await queue.get()
                yield {
                    "event": event.type,
                    "data": event.message
                }
        except asyncio.TimeoutError:
            yield ": Empty Request"
        finally:
            await eventManager.unsubscribe(queue)

    return EventSourceResponse(streamGenerator())

@app.post("/emit")
async def newEvent(event: EventModel):
    await eventManager.emit(event)
    return {"message": f"Event '{event.type}' sent to {len(eventManager.subscribers)} listeners"}
