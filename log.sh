#!/usr/bin/bash

CONTAINER="kscu-web-server"

echo "Container Logs (Traffic excluded):"
docker logs -t $CONTAINER --tail 200 | grep -i "SYSTEM"

echo "Resource Usage:"
docker stats $CONTAINER --no-stream