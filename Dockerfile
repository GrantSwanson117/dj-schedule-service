#Get OS environment
FROM python:3.14-slim

WORKDIR /dj-schedule-service

CMD ["bash"]

COPY . .