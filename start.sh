#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -c "from streak_db import init_db; init_db()"
pm2 start scheduler.py --name streak-keeper --interpreter python3
pm2 save
