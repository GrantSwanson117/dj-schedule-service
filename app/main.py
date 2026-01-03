from fastapi import FastAPI, UploadFile
from formatDB import formatDB
    
app = FastAPI()
@app.get("/")
def root():
    return {"message": "Hello, Worldaaaa!"}

@app.post("/upload-schedule/")
def upload_schedule(file: UploadFile):
    formatDB(file.filename)
    return {"status": "Schedule uploaded successfully"}
