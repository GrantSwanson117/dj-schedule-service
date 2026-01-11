import sqlite3
from datetime import datetime
from pydantic import BaseModel, Field
import formatDB

class Show(BaseModel):
    dj_name: str = Field(alias="DJ Name")
    show_name: str = Field(alias="Show Name")
    day_id: int = Field(alias="Day_ID")
    start_time: int = Field(alias="Start_Time")
    end_time: int = Field(alias="End_Time")

class Song(BaseModel):
    title: str
    artist: str
    album: str

class QueryService:

    def __init__(self, newFilename): 
        self.conn = sqlite3.connect(newFilename, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.filename = newFilename

        #self.cursor.execute('''ALTER TABLE shows RENAME COLUMN "Timeslot " TO "Timeslot"''')

    def dbTime(self):
        normalizedTime = datetime.now().hour * 60 + datetime.now().minute
        return normalizedTime
    def dbWeekday(self):
        normalizedDay = datetime.now().weekday()
        return normalizedDay
    
    def dbCurrentShow(self) -> list[Show]:
        weekday = self.dbWeekday()
        current_time = self.dbTime()
        
        print(f"DEBUG: Weekday={weekday}, Time={current_time}")
        
        self.cursor.execute(
            "SELECT * FROM shows WHERE Day_ID = ? AND Start_Time <= ? AND End_Time > ?", 
            (weekday, current_time, current_time)
        )
        shows = self.cursor.fetchall()
        for show in shows:print(show)
        if not shows: return "bruh"
        elif len(shows) > 1: return self.handleCohosts(shows)
        return shows

    def handleCohosts(self, showList):
        
        firstShow = dict(showList[0])
        djList = []
        
        for show in showList[1:]:
            if show["Show Title"] != firstShow["Show Title"]:
                return "Show scheduling error: Multiple shows in the same timeslot."
            elif show["DJ Name"] != firstShow["DJ Name"]:
                djList.append(show["DJ Name"])
        cohostString = ', '.join(djList)
        
        firstShow["DJ Name"] = cohostString
        return firstShow

    def dbFormat(self):
        formatDB.formatDB(self.filename)
    def display(self):
        self.cursor.execute('''SELECT "Day_ID", "Show Title", "DJ Name", "Start_Time", "End_Time" FROM shows''')
        rows = self.cursor.fetchall()
        for row in rows:
            print(f"Day: {row['Day_ID']} | Show: {row['Show Title']} | DJ: {row['DJ Name']} | Start Time: {row['Start_Time']} End Time: {row['End_Time']}")
    
    def dbNextShow(self) -> list[Show]:
        pass
