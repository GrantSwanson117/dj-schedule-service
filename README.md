# kscu-web-server

Developed by [GrantSwanson117](https://github.com/GrantSwanson117)<br>
[Show Recorder](https://github.com/colinfriedel/KSCURecorder2025) logic by [colinfriedel](https://github.com/colinfriedel), adapted to fit this project

A containerized backend and automation service for KSCU 103.3FM, the student-ran radio station for Santa Clara University. Features include:

- Schedule conversion/importing from a spreadsheet
- Data retrieval from database and Spotify API
- Automated show recording and delivery to DJs
- (Planned) Site Reliability Monitoring

## How It Works

This backend works in two main parts: An EC2 instance containing server logic, and a Colab script meant for schedule retrieval and delivery. 

## Instructions For Clean Installation

## Technologies Used

- Core server logic - Python, FastAPI
- Schedule Processing - Pandas, SQLite
- Starlette Server-sent Events for server -> client data transfer.
- Prometheus Monitoring