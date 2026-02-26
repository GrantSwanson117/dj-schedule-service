#! usr/bin/bash

CONTAINER = "kscu-web-server"

echo "Container Logs:"
docker logs $CONTAINER --tail 200

echo "Resource Usage:"
docker stats $CONTAINER --no-stream

echo "Network connections:"
docker exec $CONTAINER netstat -an