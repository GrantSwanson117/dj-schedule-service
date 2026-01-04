from fastapi import FastAPI, UploadFile
from formatDB import formatDB
from queryService import QueryService

db = QueryService('schedule/schedule.db')
app = FastAPI()

print(db.dbCurrentShow())

@app.get("/")
def root():
    return {"message": "Hello, Worldaaaa!"}

@app.get("/show/now/")
def getCurrentShow():
    return db.dbCurrentShow()

@app.get("/show/next/")
def getNextShow():
    return db.dbNextShow()

@app.get("/songs/previous/{amount}")
def getPreviousSongs(amount: int):
    return db.dbPreviousSongs(amount)

@app.post("/upload-schedule/")
def upload_schedule(file):
    formatDB(file.filename)
    return {"status": "Schedule uploaded successfully"}
