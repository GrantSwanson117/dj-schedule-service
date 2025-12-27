#This is a transcript of a colab notebook, which runs independently of the server. 
#That notebook is accessed by the KSCU web director to update the DJ schedule database from a google sheet, and into the EC2 instance.

"""

#When prompted, select SCU email and confirm.
import os
import gspread
import pandas as pd
from google.colab import auth
from google.auth import default

auth.authenticate_user()

creds, _ = default()

gc = gspread.authorize(creds)

ls

#Mount google drive
from google.colab import drive
drive.mount('/content/drive')

# Commented out IPython magic to ensure Python compatibility.
#Make sure this points to the KSCU main drive, where the schedule sheet is located.
#drive/Shareddrives/KSCU Main Drive
# %cd 'drive/Shareddrives/KSCU Main Drive/Archive/24-25 Archive/Programming Director'

ls

import sqlite3

#Change this filename to the name of the google sheet.
filename = "KSCU Winter '25 DJ Application (Responses)"

sh = gc.open(filename).get_worksheet(3);
if (sh):
  rows = sh.get_all_values()
  # Convert to pandas dataframe
  df = pd.DataFrame(rows[1:], columns=rows[0])

  nanValue = float("NaN")
  df.replace("", nanValue, inplace=True)

  #drop any empty columns from the dataframe
  df.dropna(how='all', axis=1, inplace=True)

  display(df)
  # Save to SQLite file

  dbFileName = filename.replace(" ", "_").replace("'", "").lower() + '.db'

  sqliteConn = sqlite3.connect(dbFileName)
  cursor = sqliteConn.cursor()
  sh2 = df.to_sql(name="shows", con=sqliteConn, if_exists='replace', index=False)
  sqliteConn.close()

  print("Google Sheet successfully converted to " + dbFileName)
else:
  print("Schedule file not found. Ensure the file is a google sheet and the path is correct.")

#Run this ONLY if AWS credentials have changed. See 'PASSWORDS' file in the KSCU drive if you run into errors later.
import awscli

!aws configure

#Send the new database file to the S3 (object storage) bucket in AWS.
import boto3
import os

s3 = boto3.resource('s3')
bucket = s3.Bucket("kscu")
dbPath = "schedule/" + dbFileName
currentPath = "schedule/"
archivePath = "schedule-archive/"

objectsToArchive = list(bucket.objects.filter(Prefix=currentPath))

if objectsToArchive:
    for obj in objectsToArchive:
        copy_source = {"Bucket": obj.bucket_name, "Key": obj.key}
        new_key = archivePath + obj.key.split('/')[-1]
        bucket.copy(copy_source, new_key)
        bucket.Object(obj.key).delete()
    print("Previous schedule(s) archived.")

bucket.upload_file(dbFileName, dbPath)

#Remove the transient google drive database
os.remove(dbFileName)
print("New schedule uploaded.")

#Create an SQS message queue to tell EC2 to grab this new file from S3 storage.

import json

sqs = boto3.resource('sqs', region_name='us-west-1')
queue = sqs.get_queue_by_name(QueueName='new-schedule-msg')
print(queue.url)

msgBody = json.dumps({
    "bucket": "kscu",
    "key": dbPath
})

response = queue.send_message(MessageBody=msgBody)
print("Notification sent to EC2. Message ID:", response.get('MessageId'))

"""