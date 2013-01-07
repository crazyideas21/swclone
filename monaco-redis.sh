cd ~/swclone
rm -f *.tmp

# ================================================
# RUNNING ON TWO MACHINES.
# ================================================

# Kill all running instances.
ssh root@dcswitch67 'killall -9 redis-server'
ssh root@dcswitch68 'killall -9 async_redis.py'

# Start redis server.
ssh root@dcswitch67 'ulimit -n 65536; cd ~/swclone/redis-stable; src/redis-server redis.conf > /dev/null' &

# Initialize server
sleep 3
ssh root@dcswitch67 'cd ~/swclone; ./async_redis.py init_server'

# Start redis clients.
ssh root@dcswitch68 'cd ~/swclone; ./async_redis.py redis'

