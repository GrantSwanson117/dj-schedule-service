from fastapi import FastAPI
import sqlite3

def initDB():
    conn = sqlite3.connect('schedules.db')
    cursor = conn.cursor()
    conn.close()
    
app = FastAPI()
@app.get("/")
def root():
    return {"message": "Hello, World!"}