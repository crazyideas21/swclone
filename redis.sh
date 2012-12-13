cd ~/swclone
rm -f *.tmp

# ================================================
# RUNNING ON TWO MACHINES.
# ================================================

# Kill all running instances.
ssh root@c08-07 'killall -9 redis-server'
ssh root@c08-08 'killall -9 async_redis.py'

# Start redis server.
ssh root@c08-07 'ulimit -n 65536; cd ~/swclone/redis-stable; src/redis-server redis.conf > /dev/null' &

# Initialize server
sleep 3
ssh root@c08-07 'cd ~/swclone; ./async_redis.py init_server'

# Start redis clients.
ssh root@c08-08 'cd ~/swclone; ./async_redis.py redis'


# # ================================================
# # RUNNING ON POD
# # ================================================

# # Kill all running instances.
# ssh root@c08-13 'killall -9 redis-server'
# for i in 14 15 16 17 18 19 20 26; do echo $i; (ssh root@c08-$i 'killall -9 simplified_redis.py' &); done
# wait

# # Start redis server.
# ssh root@c08-13 'ulimit -n 65536; cd ~/swclone/redis-stable; src/redis-server redis.conf > /dev/null' &

# # Initialize server
# sleep 3
# ssh root@c08-14 'cd ~/swclone; ./simplified_redis.py init_server'

# # Start redis clients.
# for i in 14 15 16 17 18 19 20 26; do echo $i; (ssh root@c08-$i 'cd ~/swclone; ./simplified_redis.py redis' &); done


