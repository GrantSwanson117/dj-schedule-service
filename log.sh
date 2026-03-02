#!/usr/bin/bash

CONTAINER="kscu-web-server"

echo "Container Logs (Traffic excluded):"
docker logs $CONTAINER --tail 200
# | grep "SYSTEM"

echo "Resource Usage:"
docker stats $CONTAINER --no-stream