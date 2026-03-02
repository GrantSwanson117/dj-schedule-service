import sqlite3
from datetime import datetime
import formatDB
import os
from datetime import datetime
from fastapi.responses import RedirectResponse

class QueryService:

    def __init__(self, newFilename): 
        self.filename = newFilename

        self.automationDJ: str = os.getenv("AUTOMATION_DJ").strip()
        self.automationShow: str = os.getenv("AUTOMATION_SHOW").strip()

        self.refreshToken = os.getenv("SPOTIFY_REFRESH_TOKEN").strip()

        self.clientID = os.getenv("CLIENT_ID").strip()
        self.clientSecret = os.getenv("CLIENT_SECRET").strip()
        self.redirectURI = os.getenv("REDIRECT_URI").strip()
        self.authURL = os.getenv("AUTH_URL").strip()
        self.tokenURL = os.getenv("TOKEN_URL").strip()
        self.apiBaseURL = os.getenv("API_BASE_URL").strip()

    def set_client(self, client):
        self.client = client

    @staticmethod
    def dbTime():
        return datetime.now().hour * 60 + datetime.now().minute
        
    @staticmethod
    def dbWeekday():
        return datetime.now().weekday()
         
    async def getAccessToken(self):
            response = await self.client.post(
                self.tokenURL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refreshToken,
                    "client_id": self.clientID,
                    "client_secret": self.clientSecret,
                },
            )
            data = response.json()
            return data.get("access_token")
        
    def dbCurrentShow(self):
        weekday = self.dbWeekday()
        currentTime = self.dbTime()
        with sqlite3.connect(self.filename) as conn:
            conn.row_factory = sqlite3.Row   
            rows = conn.execute(
                "SELECT rowid, * FROM shows WHERE day_id = ? AND start_time <= ? AND end_time > ?", 
                (weekday, currentTime, currentTime)
            ).fetchall()
            shows = [dict(row) for row in rows]
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
        with sqlite3.connect(self.filename) as conn:
            conn.row_factory = sqlite3.Row   
            rows = conn.execute('''SELECT "day", "show_title", "dj_name", "start_time", "end_time" FROM shows''').fetchall()
            for row in rows:
                print(f"Day: {row['day']} | Show: {row['show_title']} | DJ: {row['dj_name']} | Start Time: {row['start_time']} End Time: {row['end_time']}")
            return rows        
    def getAutoplay(self):
        return {
                "show_title": self.automationShow,
                "dj_name": self.automationDJ,
                "start_time": None,
                "end_time": None
                }
    
    def dbNextShow(self):
        day = self.dbWeekday()
        start = self.dbTime()

        validFilter = 'AND "show_title" IS NOT NULL AND "show_title" != "" AND "show_title" != ?'

        with sqlite3.connect(self.filename) as conn:
            conn.row_factory = sqlite3.Row
            slot = conn.execute(
                f"""
                SELECT day_id, start_time FROM shows 
                WHERE ((day_id > ?) OR (day_id = ? AND start_time > ?))
                {validFilter}
                ORDER BY day_id, start_time LIMIT 1
                """,
                (day, day, start, self.automationShow)
            ).fetchone()

            if slot is None:
                slot = conn.execute(
                    f'SELECT day_id, start_time FROM shows WHERE 1=1 {validFilter} ORDER BY day_id, start_time LIMIT 1',
                    (self.automationShow,)
                ).fetchone()

            if slot is None:
                return self.getAutoplay()

            rows = conn.execute(
                f'SELECT rowid, * FROM shows WHERE day_id = ? AND start_time = ? {validFilter}',
                (slot["day_id"], slot["start_time"], self.automationShow)
            ).fetchall()
            showList = [dict(r) for r in rows]

        return self.handleCohosts(showList)

    async def dbCurrentTrack(self):
        token = await self.getAccessToken()
        
        response = await self.client.get(
            f"{self.apiBaseURL}/me/player/currently-playing",
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code == 204 or response.status_code == 404:
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
    async def dbRecentTracks(self):
        token = await self.getAccessToken()
        if not token:
            return RedirectResponse(url="/login")

        response = await self.client.get(
            "https://api.spotify.com/v1/me/player/recently-played?limit=15",
            headers={"Authorization": f"Bearer {token}"}
        )
        data = response.json()

        recentTracks = []
        #Using a set to avoid duplicate songs. Check if ID was already added to set, and
        #skip if yes.
        seenIDs = set()

        index = 0
        for item in data.get('items', []):
            track = item.get('track')
            if track.get('id') in seenIDs:
                continue
            images = track.get('album', {}).get('images', [])
            releaseDate = track.get('album', {}).get('release_date', [])
            timestampLocal = item.get('played_at')
            recentTracks.append({
                "index": index,
                "name": track.get('name'),
                "artists": self.grammaticalJoin([song['name'] for song in track.get('artists', [])]),
                "link": track.get('external_urls', {}).get('spotify'),
                "played_at": timestampLocal,
                "image": images[0]['url'] if images else None,
                "release_date": releaseDate.split("-")[0] if releaseDate else None,
                "id": track.get('id')
            })
            recentTracks[index]["label"] = f"track-{index}"
            index+=1
            seenIDs.add(track.get('id'))
            if len(recentTracks) >= 10: break
            
        return recentTracks
