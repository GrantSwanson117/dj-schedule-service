import os
import io
import time
import schedule
import subprocess
import yagmail
import boto3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from queryService import QueryService

class Recorder:
    def __init__(self, db: QueryService):
        print("Recording service active.")
        self.database = db
        self.EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
        self.EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
        self.STREAM_URL = "https://kscu.streamguys1.com/live" 
        
        # AWS 
        self.S3_BUCKET = "kscu"
        self.s3_client = boto3.client('s3')

        self.last_recorded_show = None
        self.recording_lock = threading.Lock()

        self.cleanup_old_temp_files()

    def getDJ(self, show_data): 
        #Returns a list of names
        return show_data.get('dj_name')
        
    def getShowName(self, show_data): 
        return show_data.get('show_title')
    
    def getEmail(self, show_data): 
        #Returns a list of emails
        return "grantswanson62@gmail.com"
        #return show_data.get('email')
    
    def upload_to_s3(self, filepath, filename):
        print(f"Uploading {filename} to S3")
        try:
            self.s3_client.upload_file(filepath, self.S3_BUCKET, filename)
            print(f"Uploaded {filename} to S3 bucket {self.S3_BUCKET}")
            return True
        except Exception as e:
            print(f"Failed to upload to S3: {e}")
            return False
        
    def get_s3_fileobj(self, bucket, key):
        fileobj = io.BytesIO()
        self.s3_client.download_fileobj(bucket, key, fileobj)
        fileobj.seek(0)
        return fileobj

    def send_email_with_attachment(self, bucket_name, filename, dj_emails, dj_names, show_title, date_str):
        if len(dj_emails) != len(dj_names):
            print("DJ name and email mismatch. Please check database and reupload.")
            return
        
        for i in dj_names:
            url = self.s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params={'Bucket': bucket_name, 'Key': filename},
                ExpiresIn=60 * 60 * 24 * 7 
            )
            
            contents = f"""Hi {dj_names[i]},

    Your show, "{show_title}", from {date_str} has been recorded!

    You can download the recording here (the link will expire in 7 days):
    {url}

    If there are any issues with this email or the recording, please let us know by sending an email to gm@kscu.org!

    Thanks for being part of the team!
    Your friends at KSCU The Underground Sound
    """
            yag = yagmail.SMTP(self.EMAIL_ADDRESS, self.EMAIL_PASSWORD)
            try:
                yag.send(to=dj_emails[i], subject=f"Your KSCU Show Recording - {date_str}", contents=contents)
                print(f"Email sent to{dj_emails[i]}.")
                return True
            except Exception as e:
                print(f"Error sending email: {e}")
                return False
        
    def cleanup_temp_file(self, filepath):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting temp file {filepath}: {e}")

    def record_show(self, show_data):
        print("Starting show recording...")
        local_tz = ZoneInfo("America/Los_Angeles")
        recording_start_time = datetime.now(local_tz)

        dj_name = self.getDJ(show_data)
        show_title = self.getShowName(show_data)
        dj_email = self.getEmail(show_data)
        
        duration_minutes = show_data['end_time'] - show_data['start_time']
        duration_seconds = duration_minutes * 60
        duration_seconds = max(0, duration_seconds - 15)
        
        print(f"Recording started at: {recording_start_time.strftime('%H:%M:%S')}")
        print(f"DJ Info - Name: {dj_name}, Show: {show_title}, Email: {dj_email}")

        now = recording_start_time.strftime("%m-%d-%Y")
        hour = recording_start_time.strftime("%H")
        
        filename = f"{show_title.replace(' ', '_')}_{now}_{hour}00.mp3"
        filepath = f"/tmp/{filename}"

        if 1 <= recording_start_time.hour < 7:
            print("Skipping recording: between 1am and 7am.")
            return

        print(f"Starting recording for {dj_name}...")

        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", self.STREAM_URL,
                "-t", str(duration_seconds),
                "-acodec", "libmp3lame",
                filepath
            ], timeout=duration_seconds + 30, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

            if not os.path.exists(filepath):
                print(f"didn't create file: {filepath}")
                return
        except subprocess.TimeoutExpired:
            print(f"Finished recording: {filepath}")
        except Exception as e:
            print(f"Error during recording: {e}")
            return

        #Upload and email logic
        try:
            if self.upload_to_s3(filepath, filename):
                if (dj_name != "KSCU Bot") and (dj_name != "Unknown DJ") and dj_email:
                    self.send_email_with_attachment(self.S3_BUCKET, filename, dj_email, dj_name, show_title, now)
                    os.remove(filepath)
            else:
                print(f"Upload failed.")
        finally:
            self.cleanup_temp_file(filepath)
        
    def record_show_safe(self, show_data):
        if not self.recording_lock.acquire(blocking=False):
            print("Recording in progress, skipping this check")
            return
        try:
            self.record_show(show_data)
        finally:
            self.recording_lock.release()

    def record_show_threaded(self, show_data):
        threading.Thread(target=self.record_show_safe, args=(show_data,)).start()

    def cleanup_old_temp_files(self):
        try:
            temp_files = [f for f in os.listdir('/tmp') if f.endswith('.mp3')]
            for temp_file in temp_files:
                self.cleanup_temp_file(os.path.join('/tmp', temp_file))
            if temp_files:
                print(f"cleaned up {len(temp_files)} temp files on startup")
        except Exception as e:
            print(f"error cleaning old files: {e}")

    def check_and_record(self):
        show = self.database.dbCurrentShow()
        if not show or show.get('dj_name') == self.database.automationDJ:
            return

        #Create unique ID for current date and timeslot
        show_id = f"{show['rowid']}_{datetime.now().strftime('%Y-%m-%d')}"

        if self.last_recorded_show != show_id:
            self.record_show_threaded(show)
            self.last_recorded_show = show_id

    def run(self):
        schedule.every(10).seconds.do(self.check_and_record)
        while True:
            schedule.run_pending()
            time.sleep(1)