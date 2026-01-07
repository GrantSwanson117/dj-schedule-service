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
        show = self.cursor.fetchone()
        print(dict(show))
        return show
    
    def dbFormat(self):
        formatDB.formatDB(self.filename)
    
    def dbNextShow(self) -> list[Show]:
        pass
