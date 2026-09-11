#!/bin/bash
set -e
cd "."
python3 -c "from streak_db import init_db; init_db(); print('DB ready')"
pm2 delete streak-keeper 2>/dev/null || true
pm2 start scheduler.py --name streak-keeper --interpreter python3
pm2 save
pm2 status
