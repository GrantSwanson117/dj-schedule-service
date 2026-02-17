#!/usr/bin/bash

docker-compose down

docker image prune -f
docker builder prune -f --filter "until=24h"

git pull origin main

docker-compose up -d --build

echo "Web server restart successful!"