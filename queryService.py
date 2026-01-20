import sqlite3
from datetime import datetime
import formatDB
import os
import httpx
from datetime import datetime
from fastapi import Request
from fastapi.responses import RedirectResponse

class QueryService:

    def __init__(self, newFilename): 
        self.conn = sqlite3.connect(newFilename, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.filename = newFilename

        self.automationDJ: str = os.getenv("AUTOMATION_DJ").strip()
        self.automationShow: str = os.getenv("AUTOMATION_SHOW").strip()

        self.clientID = os.getenv("CLIENT_ID").strip()
        self.clientSecret = os.getenv("CLIENT_SECRET").strip()
        self.redirectURI = os.getenv("REDIRECT_URI").strip()
        self.authURL = os.getenv("AUTH_URL").strip()
        self.tokenURL = os.getenv("TOKEN_URL").strip()
        self.apiBaseURL = os.getenv("API_BASE_URL").strip()
        
    def close(self):
        if self.conn:
            self.conn.close()

    @staticmethod
    def dbTime():
        return datetime.now().hour * 60 + datetime.now().minute
        
    @staticmethod
    def dbWeekday():
        return datetime.now().weekday()
         
    
    def dbCurrentShow(self):
        weekday = self.dbWeekday()
        currentTime = self.dbTime()
        
        print(f"DEBUG: Weekday={weekday}, Time={currentTime}")
        
        self.cursor.execute(
            "SELECT rowid, * FROM shows WHERE day_id = ? AND start_time <= ? AND end_time > ?", 
            (weekday, currentTime, currentTime)
        )
        shows = self.cursor.fetchall()
        if not shows: 
            return self.getAutoplay()
        return self.handleCohosts(shows)

    def handleCohosts(self, showList):
        if not showList: return self.getAutoplay()
        firstShow = dict(showList[0])
        djList = [firstShow["dj_name"]]
        nameList = [firstShow["name"]]
        emailList = [firstShow["email"]]
        
        for show in showList[1:]:
            if show["show_title"] != firstShow["show_title"]:
                raise ValueError("Show scheduling error: Multiple shows in the same timeslot.")
            elif show["dj_name"] != firstShow["dj_name"]:
                djList.append(show["dj_name"])
                emailList.append(show["email"])
                nameList.append(show["name"])
        
        firstShow["dj_name"] = self.grammaticalJoin(djList)
        firstShow["name"] = nameList
        firstShow["email"] = emailList
        return firstShow

    def dbFormat(self):
        formatDB.formatDB(self.filename)

    @staticmethod
    def grammaticalJoin(list):
        cleanedList = [i.strip() for i in list if i]
        return ", ".join(cleanedList[:-2] + [" & ".join(cleanedList[-2:])])
    
    def display(self):
        self.cursor.execute('''SELECT "day_id", "show_title", "dj_name", "start_time", "end_time" FROM shows''')
        rows = self.cursor.fetchall()
        for row in rows:
            print(f"Day: {row['day_id']} | Show: {row['show_title']} | DJ: {row['dj_name']} | Start Time: {row['start_time']} End Time: {row['end_time']}")
    
    def getAutoplay(self):
        return {
                "show_title": self.automationShow,
                "dj_name": self.automationDJ
                }
    
    def dbNextShow(self):
        day = self.dbWeekday()
        start = self.dbTime()

        validFilter = 'AND "show_title" IS NOT NULL AND "show_title" != "" AND "show_title" != ?'

        # Query 1: Find the next valid slot
        self.cursor.execute(
            f"""
            SELECT day_id, start_time FROM shows 
            WHERE ((day_id > ?) OR (day_id = ? AND start_time > ?))
            {validFilter}
            ORDER BY day_id, start_time LIMIT 1
            """,
            (day, day, start, self.automationShow)
        )
        slot = self.cursor.fetchone()

        if slot is None:
            self.cursor.execute(
                f'SELECT day_id, start_time FROM shows WHERE 1=1 {validFilter} ORDER BY day_id, start_time LIMIT 1',
                (self.automationShow,)
            )
            slot = self.cursor.fetchone()

        if slot is None:
            return self.getAutoplay()

        self.cursor.execute(
            f'SELECT rowid, * FROM shows WHERE day_id = ? AND start_time = ? {validFilter}',
            (slot["day_id"], slot["start_time"], self.automationShow)
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
            "artists": self.grammaticalJoin([song['name'] for song in track.get('artists', [])]),
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
        #Using a set to avoid duplicate songs. Check if ID was already added to set, and
        #skip if yes.
        seenIDs = set()

        index = 1
        for item in data.get('items', []):
            track = item.get('track')
            if track.get('id') in seenIDs:
                continue
            images = track.get('album', {}).get('images', [])
            releaseDate = track.get('album', {}).get('release_date', [])
            recentTracks.append({
                "index": index,
                "name": track.get('name'),
                "artists": self.grammaticalJoin([song['name'] for song in track.get('artists', [])]),
                "link": track.get('external_urls', {}).get('spotify'),
                "played_at": item.get('played_at'),
                "image": images[0]['url'] if images else None,
                "release_date": releaseDate.split("-")[0] if releaseDate else None,
                "id": track.get('id')
            })
            index+=1
            seenIDs.add(track.get('id'))
            if len(recentTracks) >= 10: break
        return recentTracks
