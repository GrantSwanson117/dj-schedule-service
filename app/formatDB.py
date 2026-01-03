import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

global cursor
conn = None

def addNewColumns(columnList):
    cursor.execute(f"PRAGMA table_info('shows');")
    columns = [row[1] for row in cursor.fetchall()]
    for i in columnList:
        if i not in columns:
            cursor.execute(f'ALTER TABLE shows ADD COLUMN {i} INT')
    print("Database columns set.")
    

def normalizeTime(timeStr):
    
    if '-' not in timeStr:
        print('Time formatted incorrectly. Ensure a dash sits between the times and AM/PM is specified at the end.')
        return
    
    strippedTime = timeStr.replace(" ", "").replace(".", "").replace("(cohost)", "").lower()

    ampm = strippedTime[-2:]
    if ampm not in ('am', 'pm'):
        print('Time formatted incorrectly. Ensure AM/PM is specified at the end.')
        return

    strippedTime = strippedTime.replace('am', '').replace('pm', '')
    parts = strippedTime.split('-')

    if len(parts) != 2:
        print('Time formatted incorrectly.')
        return

    times = []
    for part in parts:
        hours, minutes = normalizePart(part)
        times.append((hours, minutes))

    endDatetime = toDatetime(times[1], ampm)
    startDatetime = toDatetime(times[0], ampm)

    if startDatetime > endDatetime:
        startDatetime -= timedelta(hours=12)
    startDatetime = startDatetime.hour * 60 + startDatetime.minute
    endDatetime = endDatetime.hour * 60 + endDatetime.minute
            
    return startDatetime, endDatetime


def normalizePart(part):

    if ':' in part:
        h, m = part.split(':')
    elif len(part) <= 2:
        h, m = part, '00'
    else:
        h, m = part[:-2], part[-2:]

    return int(h), int(m)

def toDatetime(time_tuple, ampm):
    h, m = time_tuple
    
    if ampm == 'pm' and h != 12:h += 12
    if ampm == 'am' and h == 12: h = 0
    return datetime(2000, 1, 1, h, m)

def setTimeslots():
    rows = cursor.execute("SELECT rowid, Timeslot FROM shows;").fetchall()

    for rowid, timeslot in rows:
        normalized = normalizeTime(timeslot)
        if normalized:
            start, end = normalized
            cursor.execute(
                'UPDATE shows SET "Start_Time" = ?, "End_Time" = ? WHERE rowid = ?',
                (start, end, rowid)
            )
    print("Timeslots set.")

def setDayIDs():
    dayIDs = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    cursor.execute("UPDATE shows SET Day = LOWER(REPLACE(Day, ' ', ''))")
    for day, id in dayIDs.items():
        cursor.execute('UPDATE shows SET "Day_ID" = ? WHERE "Day" = ?', (id, day))
    print("Day IDs set.")

requiredColumns = ["day", "timeslot", "show title", "dj name"]
newColumns = ["Start_Time", "End_Time", "Day_ID"]

def formatDB(filename):
    conn = sqlite3.connect(filename)
    global cursor
    cursor = conn.cursor()
    addNewColumns(newColumns)
    setTimeslots()
    setDayIDs()
    conn.commit()
    cursor.execute("VACUUM;")
    conn.close()
