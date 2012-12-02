cd ~/swclone
rm *.tmp

ssh root@c08-13 'killall -9 redis-server'

for i in 14 15 16 17 18 19 20 26; do echo $i; (ssh root@c08-$i 'killall -9 simplified_redis.py' &); done
wait

ssh root@c08-13 'ulimit -n 65536; cd ~/swclone/redis-stable; src/redis-server redis.conf > /dev/null' &

sleep 3

ssh root@c08-14 'cd ~/swclone; ./simplified_redis.py init_server'

for i in 14 15 16 17 18 19 20 26; do echo $i; (ssh root@c08-$i 'cd ~/swclone; ./simplified_redis.py redis' &); done


