import sqlite3
from datetime import datetime
import formatDB
import os
import httpx
from datetime import datetime
import urllib.parse
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

class QueryService:

    def __init__(self, newFilename): 
        self.conn = sqlite3.connect(newFilename, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.filename = newFilename
        self.automationDJ = "KSCU Bot"
        self.automationShow = "KSCU Autoplay"

        self.clientID = os.getenv("CLIENT_ID").strip()
        self.clientSecret = os.getenv("CLIENT_SECRET").strip()
        self.redirectURI = os.getenv("REDIRECT_URI").strip()
        self.authURL = os.getenv("AUTH_URL").strip()
        self.tokenURL = os.getenv("TOKEN_URL").strip()
        self.apiBaseURL = os.getenv("API_BASE_URL").strip()
        
    def close(self):
        if self.conn:
            self.conn.close()

    def dbTime(self):
        return datetime.now().hour * 60 + datetime.now().minute
        
    def dbWeekday(self):
        return datetime.now().weekday()
         
    
    def dbCurrentShow(self):
        weekday = self.dbWeekday()
        currentTime = self.dbTime()
        
        print(f"DEBUG: Weekday={weekday}, Time={currentTime}")
        
        self.cursor.execute(
            "SELECT rowid, * FROM shows WHERE Day_ID = ? AND Start_Time <= ? AND End_Time > ?", 
            (weekday, currentTime, currentTime)
        )
        shows = self.cursor.fetchall()
        if not shows: 
            return self.getAutoplay()
        elif len(shows) > 1: return self.handleCohosts(shows)
        return self.handleCohosts(shows)

    def handleCohosts(self, showList):
        firstShow = dict(showList[0])
        djList = [firstShow["DJ Name"]]
        nameList = [firstShow["Name"]]
        emailList = [firstShow["Email"]]
        
        for show in showList[1:]:
            if show["Show Title"] != firstShow["Show Title"]:
                raise ValueError("Show scheduling error: Multiple shows in the same timeslot.")
            elif show["DJ Name"] != firstShow["DJ Name"]:
                djList.append(show["DJ Name"])
                emailList.append(show["Email"])
                nameList.append(show["Name"])
        
        firstShow["DJ Name"] = self.grammaticalJoin(djList)
        firstShow["Name"] = nameList
        firstShow["Email"] = emailList
        return firstShow

    def dbFormat(self):
        formatDB.formatDB(self.filename)

    def grammaticalJoin(self, list):
        cleanedList = [i.strip() for i in list if i is not None]
        return ", ".join(cleanedList[:-2] + [" and ".join(cleanedList[-2:])])
    
    def display(self):
        self.cursor.execute('''SELECT "Day_ID", "Show Title", "DJ Name", "Start_Time", "End_Time" FROM shows''')
        rows = self.cursor.fetchall()
        for row in rows:
            print(f"Day: {row['Day_ID']} | Show: {row['Show Title']} | DJ: {row['DJ Name']} | Start Time: {row['Start_Time']} End Time: {row['End_Time']}")
    
    def getAutoplay(self):
        return {
                "Show Title": self.automationShow,
                "DJ Name": self.automationDJ
                }
    
    def dbNextShow(self):
        currentShow = self.dbCurrentShow()
        if not currentShow: return self.getAutoplay()

        day = currentShow["Day_ID"]
        start = currentShow["Start_Time"]

        self.cursor.execute(
            """
            SELECT Day_ID, Start_Time FROM shows WHERE (Day_ID > ?)
            OR (Day_ID = ? AND Start_Time > ?) ORDER BY Day_ID, Start_Time LIMIT 1
            """,
            (day, day, start)
        )
        slot = self.cursor.fetchone()

        if slot is None:
            self.cursor.execute(
                """SELECT Day_ID, Start_Time FROM shows
                ORDER BY Day_ID, Start_Time LIMIT 1"""
            )
            slot = self.cursor.fetchone()

        self.cursor.execute(
            """ SELECT rowid, * FROM shows WHERE Day_ID = ? AND Start_Time = ?""",
            (slot["Day_ID"], slot["Start_Time"])
        )
        rows = self.cursor.fetchall()

        return self.handleCohosts(rows)

    async def dbCallback(self, request: Request):
        code = request.query_params.get('code')
        error = request.query_params.get('error')

        if error:
            return {"error": error}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.tokenURL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': self.redirectURI,
                    'client_id': self.clientID,
                    'client_secret': self.clientSecret,
                }
            )
        
        token_info = response.json()
        request.session['access_token'] = token_info.get('access_token')
        request.session['refresh_token'] = token_info.get('refresh_token')
        request.session['expires_at'] = datetime.now().timestamp() + token_info.get('expires_in', 3600)
        
        return RedirectResponse(url="/tracks/current")
    
    async def dbCurrentTrack(self, request: Request):
        access_token = request.session.get('access_token')
        expires_at = request.session.get('expires_at')

        if not access_token:
            return RedirectResponse(url="/login")
        
        if expires_at and datetime.now().timestamp() > expires_at:
            return RedirectResponse('/refresh-token')
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.apiBaseURL}/me/player/currently-playing",
                headers={"Authorization": f"Bearer {access_token}"}
            )

        if response.status_code == 204:
            return {"message": "No track currently playing"}
        
        data = response.json()
        track = data.get('item')
        if not track:
            return {"message": "Unable to retrieve track info"}
        images = track.get('album', {}).get('images', [])
        releaseDate = track.get('album', {}).get('release_date', [])
        return {
            "id": track.get('id'),
            "name": track.get('name'),
            "artists": ", ".join([artist['name'] for artist in track.get('artists', [])]),
            "link": track.get('external_urls', {}).get('spotify'),
            "image": images[0]['url'] if images else None,
            "release_date": releaseDate.split("-")[0] if releaseDate else None,
        }
    async def dbGetRecentTracks(self, request: Request):
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
            images = track.get('album', {}).get('images', [])
            releaseDate = track.get('album', {}).get('release_date', [])
            recentTracks.append({
                "name": track.get('name'),
                "artists": self.grammaticalJoin([song['name'] for song in track.get('artists', [])]),
                "played_at": item.get('played_at'),
                "image": images[0]['url'] if images else None,
                "release_date": releaseDate.split("-")[0] if releaseDate else None,
                "id": track.get('id')
            })
        return recentTracks
