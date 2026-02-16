import os
import io
import time
import schedule
import subprocess
import yagmail
import boto3
import threading
from textwrap import dedent
from datetime import datetime
from zoneinfo import ZoneInfo
from queryService import QueryService

class ShowRecorder:
    def __init__(self, db: QueryService):
        print("Recording service active.")
        self.database = db
        self.EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS").strip()
        self.EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD").strip()
        self.STREAM_URL = "https://kscu.streamguys1.com/live" 

        
        # AWS 
        self.S3_BUCKET = "kscu"
        aws_access = os.getenv("AWS_ACCESS_KEY_ID").strip()
        aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY").strip()
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access,
            aws_secret_access_key=aws_secret,
            region_name="us-west-1"
        )

        self.last_recorded_show = None
        self.recording_lock = threading.Lock()

        self.cleanup_old_temp_files()

    @staticmethod
    def recorderHealthCheck():
        return{"Status:": "OK"}

    @staticmethod
    def getName(show_data) -> list: 
        return list(show_data.get('name'))  if show_data else []

    @staticmethod
    def getShowName(show_data) -> str: 
        return show_data.get('show_title') if show_data else ""
    
    @staticmethod
    def getDJ(show_data) -> str: 
        return show_data.get('dj_name') if show_data else []
    
    @staticmethod
    def getEmail(show_data) -> list: 
        #Test case: return["yourpersonalemail@xyz.com"]. 
        #I f the current show is a cohosted show, it would be return["yourpersonalemail@xyz.com", "yourpersonalemail@xyz.com"]
        #return list(show_data.get('email'))
        return ["grantswanson62@gmail.com"]
    
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

    def send_email_with_attachment(self, bucket_name, filename, dj_emails, names, show_title, date_str):
        if len(dj_emails) != len(names):
            print("DJ name and email mismatch. Please check database and reupload.")
            return False
            
        url = self.s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket_name, 'Key': filename},
            ExpiresIn=60 * 60 * 24 * 7
        )
        
        yag = yagmail.SMTP(self.EMAIL_ADDRESS, self.EMAIL_PASSWORD)
        success = True

        for i, name in enumerate(names):
            contents = dedent(f"""\
                Hi {name},

                Your show, "{show_title}", from {date_str} has been recorded!

                You can download the recording here (the link will expire in 7 days):
                {url}

                If there are any issues, email gm@kscu.org!

                Your friends at KSCU The Underground Sound""").strip()
            try:
                yag.send(to=dj_emails[i], subject=f"Your KSCU Show Recording - {date_str}", contents=contents)
                print(f"Email sent to {dj_emails[i]}.")
            except Exception as e:
                print(f"Error sending email to {dj_emails[i]}: {e}")
                success = False
            
            return success
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

        names = self.getName(show_data)
        show_title = self.getShowName(show_data)
        dj_emails = self.getEmail(show_data)
        
        print(f"Recording started at: {recording_start_time.strftime('%H:%M:%S')}")
        print(f"DJ Info - Name: {names}, Show: {show_title}")

        now = recording_start_time.strftime("%m-%d-%Y")
        hour = recording_start_time.strftime("%H")
        
        safe_title = "".join([c if c.isalnum() else "_" for c in show_title])
        filename = f"{safe_title}_{now}_{hour}00.mp3"
        filepath = f"/tmp/{filename}"

        if 1 <= recording_start_time.hour < 7:
            print("Skipping recording: between 1am and 7am.")
            return

        try:
            self.current_process = subprocess.Popen([
                "ffmpeg", "-y", "-i", self.STREAM_URL,
                "-acodec", "libmp3lame",
                filepath
            ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

            print(f"FFmpeg started.")
            
            self.current_process.wait()
            print(f"FFmpeg process finished for {show_title}.")

        except Exception as e:
            print(f"Error during recording: {e}")
            return

        try:
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                if self.upload_to_s3(filepath, filename):
                    check_name = names[0] if isinstance(names, list) else names
                    if check_name not in ["KSCU Bot", "Unknown DJ"]:
                        self.send_email_with_attachment(self.S3_BUCKET, filename, dj_emails, names, show_title, now)
                    os.remove(filepath)
            else:
                print(f"File {filepath} was empty or not found. Skipping upload.")
        except Exception as e:
            print(f"Failed post-recording steps: {e}")
        finally:
            self.cleanup_temp_file(filepath)
        
    def record_show_safe(self, show_data):
        if not self.recording_lock.acquire():
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
        try:
            show = self.database.dbCurrentShow()
            if not show:
                return

            #Building unique ID for show
            rowid = show.get('rowid', 'unknown')
            show_id = f"{rowid}_{datetime.now().strftime('%Y-%m-%d')}"

            if self.last_recorded_show != show_id:
                
                if hasattr(self, 'current_process') and self.current_process.poll() is None:
                    print(f"Ending current recording to start new show or automation.")
                    self.current_process.terminate()
                    
                    #Buffer to let other threads finish
                    time.sleep(3)

                dj = show.get('dj_name')
                
                if dj != self.database.automationDJ:
                    print(f"New show detected: {show['show_title']} - {dj}")
                    self.record_show_threaded(show)
                    self.last_recorded_show = show_id
                else:
                    print("Automated show.")
                    self.last_recorded_show = show_id

        except Exception as e:
            print(f"Check error: {e}")

    def run(self):
        schedule.every(60).seconds.do(self.check_and_record)
        while True:
            schedule.run_pending()
            time.sleep(1)