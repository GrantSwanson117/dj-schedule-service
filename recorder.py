import os
import io
import time
import schedule
import subprocess
import yagmail
import requests
import json
import pytz
import boto3
import threading
from botocore.exceptions import NoCredentialsError, ClientError
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from queryService import QueryService
from dotenv import load_dotenv 

class Recorder:

    def __init__(self, db: QueryService):
        #AWS variables
        self.emailAddress = os.getenv("EMAIL_ADDRESS").strip()
        self.emailPassword = os.getenv("EMAIL_PASSWORD").strip()
        self.s3client = boto3.client('s3')
        self.streamURL = "https://kscu.streamguys1.com/live" 
        self.self.s3bucket = "kscu"
        recordingLock = threading.Lock()

    def isNowInShow(self, now_time, start_time, end_time):
        #overnight shows fix
        if start_time <= end_time:
            return start_time <= now_time < end_time
        else:
            return now_time >= start_time or now_time < end_time

    def uploadToS3(self, filepath, filename):
        print(f"Uploading {filename} to S3")
        try:
            self.s3client.upload_file(filepath, self.s3bucket, filename)
            print(f"Uploaded {filename} to S3 bucket {self.s3bucket}")
            return True
        except Exception as e:
            print(f"Failed to upload to S3: {e}")
            return False
        
    def getS3FileObj(self, bucket, key):
        fileobj = io.BytesIO()
        self.s3client.download_fileobj(bucket, key, fileobj)
        fileobj.seek(0)
        return fileobj

    def getDjFromSchedule(self, target_time, schedule_file="schedule.json"):
        with open(schedule_file, "r") as f:
            schedule = json.load(f)

        # Use PST instead of UTC
        local_tz = pytz.timezone("America/Los_Angeles")
        current_day = target_time.strftime("%A") 
        current_time = target_time.strftime("%H:%M")

        for show in schedule:
            if show["day"] == current_day:
                if show["start_time"] <= current_time < show["end_time"]:
                    return show["dj_name"], show["title"], show["dj_email"], show["start_time"], show["end_time"]

        return "Unknown DJ", "Unknown Show", None, None, None

    def getShowDurationMinutes(self, start_time, end_time):
        fmt = "%H:%M"
        start = datetime.strptime(start_time, fmt)
        end = datetime.strptime(end_time, fmt)

        if end <= start:
            end += timedelta(days=1)

        return int((end - start).total_seconds() / 60)

    def sendEmailWithAttachment(self, bucket_name, filename, dj_email, dj_name, show_title, date_str):
        
        url = self.s3client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket_name, 'Key': filename},
            ExpiresIn=60 * 60 * 24 * 7 # (7 days in seconds format)
        )
        
        contents = f"""Hi {dj_name},

    Your show, "{show_title}", from {date_str} has been recorded!

    You can download the recording here (the link will expire in 7 days):
    {url}

    If there are any issues with this email or the recording, please let us know by sending an email to gm@kscu.org!

    Thanks for being part of the team!
    Your friends at KSCU The Underground Sound
    """
        yag = yagmail.SMTP(self.emailAddress, self.emailPassword)
        try:
            result = yag.send(
                to=dj_email,
                subject=f"Your KSCU Show Recording - {date_str}",
                contents=contents
            )
            print(f"Email sent.")
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
        
    def cleanupTempFile(self, filepath):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting temp file {filepath}: {e}")

    def recordShow(self):
        local_tz = ZoneInfo("America/Los_Angeles")
        recording_start_time = datetime.now(local_tz)

        dj_name, show_title, dj_email, start_time, end_time = self.getDjFromSchedule(recording_start_time)

        #skips recording for unknown shows
        if dj_name == "Unknown DJ" or not start_time or not end_time:
            print("No scheduled show found, skipping recording")
            return

        duration_minutes = self.getShowDurationMinutes(start_time, end_time)
        duration_seconds = duration_minutes * 60
        duration_seconds = max(0, duration_seconds - 10) #little buffer idk if we need it or not
        
        print(f"Recording started at: {recording_start_time.strftime('%H:%M:%S')}")
        print(f"DJ Info - Name: {dj_name}, Show: {show_title}, Email: {dj_email}")

        now = recording_start_time.strftime("%m-%d-%Y")
        hour = recording_start_time.strftime("%H")
        
        filename = f"{show_title}_{now}_{hour}00.mp3"
        filepath = f"/tmp/{filename}"

        if 1 <= recording_start_time.hour < 7:
            print("Skipping recording: between 1am and 7am.")
            return

        print(f"Starting recording for {dj_name}...")

        try:
            subprocess.run([
                "ffmpeg",
                "-y",
                "-i", self.streamURL,
                "-t", str(duration_seconds),
                "-acodec", "libmp3lame",
                filepath
            ], timeout = duration_seconds + 30)

            if not os.path.exists(filepath):
                print(f"didn't create file: {filepath}")
                return
        except subprocess.TimeoutExpired:
            print(f"Finished recording: {filepath}")
        except Exception as e:
            print(f"Error during recording: {e}")
            return
        finally:
            #cleans temp tile if it's not successful
            pass

        # Send email
        try:
            print("Starting upload to S3")
            if self.uploadToS3(filepath, filename):
                print("upload succeeded")
                if (dj_name != "KSCU Bot") and (dj_name != "Unknown DJ"):
                    if (self.sendEmailWithAttachment(self.s3bucket, filename, dj_email, dj_name, show_title, now)):
                        print(f"Email sent.")
                        os.remove(filepath)
                        print(f"Deleted local file {filepath}.")
                    else:
                        print(f"Email sending failed, keeping local file.")
                else:
                    print(f"Bot show, didn't send email")
            else:
                print(f"Upload to S3 failed, skipping email and keeping local file.")
        except Exception as e:
            print(f"Failed to send email or upload file: {e}")
        finally:
            self.cleanupTempFile(filepath)
        
    def recordShowSafe(self):
        if not self.recordingLock.acquire(blocking=False):
            print("Recording in progress, skipping this hour")
            return
        
        try:
            self.c()
        finally:
            self.recordingLock.release()

    def recordShowThreaded(self):
        threading.Thread(target=self.recordShowSafe).start()

    def cleanupOldTempFiles():
        #cleans old files on startup
        try:
            temp_files = [f for f in os.listdir('/tmp') if f.endswith('.mp3')]
            for temp_file in temp_files:
                filepath = f"/tmp/{temp_file}"
                self.cleanupTempFile(filepath)
            if temp_files:
                print(f"cleaned up {len(temp_files)} temp files on startup)")
        except Exception as e:
            print(f"error cleaning old files: {e}")

    cleanupOldTempFiles()

    last_recorded_show = None

    def checkAndRecord(self):
        global last_recorded_show
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        dj_name, show_title, dj_email, start_time, end_time = self.getDjFromSchedule(now)

        now_time = now.strftime("%H:%M")

        if dj_name != "Unknown DJ" and start_time and end_time:
            show_id = f"{dj_name}_{show_title}_{start_time}_{end_time}_{now.date()}"

            if self.isNowInShow(now_time, start_time, end_time) and last_recorded_show != show_id:
                print(f"Recording started for {show_title} ({dj_name})")
                self.recordShow()
                last_recorded_show = show_id
                
    schedule.every(30).seconds.do(checkAndRecord)

    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nScheduler stopped by user")
    except Exception as e:
        print(f"Scheduler error: {e}")
        time.sleep(60)