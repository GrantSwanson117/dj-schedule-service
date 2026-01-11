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

CLIENT_ID = os.getenv("CLIENT_ID").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI").strip().replace("'", "")

AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1'

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
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': " ".join(scopes),
        'redirect_uri': REDIRECT_URI,
        'show_dialog': 'false'
    }
    auth_link = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_link)

@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get('code')
    error = request.query_params.get('error')

    if error:
        return {"error": error}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': REDIRECT_URI,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
            }
        )
    
    token_info = response.json()
    request.session['access_token'] = token_info.get('access_token')
    request.session['refresh_token'] = token_info.get('refresh_token')
    request.session['expires_at'] = datetime.now().timestamp() + token_info.get('expires_in', 3600)
    
    return RedirectResponse(url="/tracks/current")

@app.get("/tracks/current/")
async def current_track(request: Request):
    access_token = request.session.get('access_token')
    expires_at = request.session.get('expires_at')

    if not access_token:
        return RedirectResponse(url="/login")
    
    if expires_at and datetime.now().timestamp() > expires_at:
        return RedirectResponse('/refresh-token')
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/me/player/currently-playing",
            headers={"Authorization": f"Bearer {access_token}"}
        )

    if response.status_code == 204:
        return {"message": "No track currently playing"}
    
    data = response.json()
    item = data.get('item')
    if not item:
        return {"message": "Unable to retrieve track info"}

    return {
        "id": item.get('id'),
        "name": item.get('name'),
        "artists": ", ".join([artist['name'] for artist in item.get('artists', [])]),
        "link": item.get('external_urls', {}).get('spotify')
    }

@app.get("/refresh-token")
async def refreshToken(request: Request):
    refresh_token = request.session.get('refresh_token')
    
    if not refresh_token:
        return RedirectResponse('/login')
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET
            }
        )
        
    new_token_info = response.json()
    
    request.session['access_token'] = new_token_info.get('access_token')
    request.session['expires_at'] = datetime.now().timestamp() + new_token_info.get('expires_in', 3600)

    return RedirectResponse("/tracks/current")

@app.get("/shows/current/")
def getCurrentShow():
    return db.dbCurrentShow()

@app.get("/shows/next/")
def getNextShow():
    return db.dbNextShow()

@app.get("/tracks/recent/{amount}")
async def get_recent_tracks(amount: int, request: Request):
    token = request.session.get('access_token')
    if not token:
        return RedirectResponse(url="/login")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.spotify.com/v1/me/player/recently-played",
            headers={"Authorization": f"Bearer {token}"}
        )
        data = response.json()
    
    recentTracks = []
    for item in data.get('items', []):
        track = item.get('track')
        recentTracks.append({
            "name": track.get('name'),
            "artists": [song['name'] for song in track.get('artists', [])],
            "played_at": item.get('played_at'),
            "id": track.get('id')
        })
    return recentTracks

@app.post("/upload-schedule/")
def upload_schedule(file):
    formatDB(file.filename)
    return {"status": "Schedule uploaded successfully"}