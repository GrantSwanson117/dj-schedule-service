import sqlite3
from datetime import datetime
from pydantic import BaseModel, Field

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
    def __init__(self, filename): 
        self.conn = sqlite3.connect(filename)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def dbTime(self):
        normalizedTime = datetime.now().hour * 60 + datetime.now().minute
        return normalizedTime
    def dbWeekday(self):
        normalizedDay = datetime.now().weekday()
        return normalizedDay
    def dbCurrentShow(self) -> list[Show]:
        showList = []
        self.cursor.execute("SELECT * FROM shows WHERE Day_ID = ? AND Start_Time <= ? AND End_Time > ?", (self.dbWeekday(), self.dbTime(), self.dbTime()))
        for row in self.cursor.fetchall():
            showList.append(Show(**row))
        return showList
    
    def dbNextShow(self) -> list[Show]:
        pass