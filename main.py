import os
import httpx
import formatDB 
from datetime import datetime
import urllib.parse
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from queryService import QueryService

load_dotenv()

tokenURL = os.getenv("TOKEN_URL").strip()
clientID = os.getenv("CLIENT_ID").strip()
clientSecret = os.getenv("CLIENT_SECRET").strip()
authURL = os.getenv("AUTH_URL").strip()
redirectURI = os.getenv("REDIRECT_URI").strip()

db = QueryService('schedule.db')
db.dbFormat()
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SPOTIFY_SECRET_KEY"))

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

@app.post("/upload-schedule/")
def uploadSchedule(file):
    formatDB(file.filename)
    return {"status": "Schedule uploaded successfully"}

@app.get("/shows/current/")
def getCurrentShow():
    return db.dbCurrentShow()

@app.get("/shows/next/")
def getNextShow():
    return db.dbNextShow()    