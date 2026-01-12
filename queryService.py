import sqlite3
from datetime import datetime
import formatDB

class QueryService:

    def __init__(self, newFilename): 
        self.conn = sqlite3.connect(newFilename, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.filename = newFilename
        self.automationDJ = "KSCU Bot"
        self.automationShow = "KSCU Autoplay"

    def close(self):
        if self.conn:
            self.conn.close()

    def dbTime(self):
        normalizedTime = datetime.now().hour * 60 + datetime.now().minute
        return normalizedTime
    def dbWeekday(self):
        normalizedDay = datetime.now().weekday()
        return normalizedDay
    
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
        return list(shows)

    def handleCohosts(self, showList):
        
        firstShow = dict(showList[0])
        djList = [firstShow["DJ Name"]]
        
        for show in showList[1:]:
            if show["Show Title"] != firstShow["Show Title"]:
                raise ValueError("Show scheduling error: Multiple shows in the same timeslot.")
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
    
    def getAutoplay(self):
        return {
                "Show Title": self.automationShow,
                "DJ Name": self.automationDJ
                }
    def dbNextShow(self):
        currentShow = self.dbCurrentShow()
        if not currentShow: return self.getAutoplay()

        day = currentShow[0]["Day_ID"]
        start = currentShow[0]["Start_Time"]

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
            """ SELECT * FROM shows WHERE Day_ID = ? AND Start_Time = ?""",
            (slot["Day_ID"], slot["Start_Time"])
        )
        rows = self.cursor.fetchall()

        return self.handleCohosts(rows)

