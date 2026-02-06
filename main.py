import os
import httpx
import formatDB 
import urllib.parse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from queryService import QueryService
from eventManager import SSEEventManager, EventModel
from dotenv import load_dotenv

#from recorder import Recorder

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

#Show recorder instantiation
#rc = Recorder(db)

app = FastAPI()

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SPOTIFY_SECRET_KEY")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@asynccontextmanager
def startWatchdog():
    asyncio.create_task(trackWatchdog())
    #asyncio.create_task(showWatchdog())

async def trackWatchdog():
    prevTrack = None
    curTrack = currentTrack()
    if curTrack != prevTrack:
        await eventManager.emit(EventModel(
            type = "trackUpdate",
            message = f"Now playing: {currentTrack['title']}"
        ))
        prevTrack = curTrack
        await asyncio.sleep(10)

@app.get("/")
def root(): return {
    "Hello!": "welcome to the KSCU web server! the following endpoints are used for data fetching and monitoring.",
    "/": "root, for help and info",
    "/shows/current": "show currently playing",
    "/shows/next": "next show scheduled to play (ignoring automated shows)",
    "/tracks/current": "current track playing",
    "/tracks/recent": "returns the 20 most recently played tracks",
    "/metrics": "used for Grafana monitoring",
    "/upload-schedule (POST)": "used for sending a schedule database at the beginning of a new quarter, or to replace an existing one",
}

@app.get("/healthcheck")
def healthCheck(): return {"Status:": "OK"}

@app.get("/login")
async def login():
    scopes = [
    "user-read-currently-playing",
    "user-read-recently-played"
]
    params = {
        'client_id': clientID,
        'response_type': 'code',
        'scope': " ".join(scopes),
        'redirect_uri': redirectURI,
        'show_dialog': 'false'
    }
    auth_link = f"{authURL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_link)  

@app.get("/refresh-token")
async def refreshToken(request: Request):
    refresh_token = request.session.get('refresh_token')
        
    if not refresh_token:
        return RedirectResponse('/login')
        
    async with httpx.AsyncClient() as client:
        response = await client.post(
            tokenURL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': clientID,
                'client_secret': clientSecret
            }
        )
        
    new_token_info = response.json()
    
    request.session['access_token'] = new_token_info.get('access_token')
    request.session['expires_at'] = datetime.now().timestamp() + new_token_info.get('expires_in', 3600)

    return RedirectResponse("/tracks/current")

@app.get("/callback")
async def callback(request: Request):
    return await db.dbCallback(request)

@app.get("/tracks/current/")
async def currentTrack(request: Request):
    return await db.dbCurrentTrack(request)

#Returns 20 most recent tracks
@app.get("/tracks/recent/")
async def get_recent_tracks(request: Request):
    return await db.dbGetRecentTracks(request)

@app.get("/shows/current/")
def getCurrentShow():
    return db.dbCurrentShow()

@app.get("/shows/next/")
def getNextShow():
    return db.dbNextShow()    

@app.get("/stream")
async def streamEvents(request: Request):
    queue = await eventManager.subscribe()

    async def streamGenerator():
        try:
            while True:
                # Check if client is still there
                if await request.is_disconnected():
                    break
                
                event = await queue.get()
                yield {
                    "event": event.type,
                    "data": event.message
                }
        finally:
            eventManager.unsubscribe(queue)

    return EventSourceResponse(streamGenerator())

@app.post("/emit")
async def newEvent(event: EventModel):
    await eventManager.emit(event)
    return {"message": f"Event '{event.type}' sent to {len(eventManager.subscribers)} listeners"}

@app.post("/upload-schedule/")
def uploadSchedule(file, background_tasks: BackgroundTasks):
    background_tasks.add_task(formatDB, file.filename)
    return {"status": "Schedule received; Processing."}
