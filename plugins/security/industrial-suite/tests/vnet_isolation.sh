#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
# FreeBSD-only integration check. Configure the documented review access matrix first.
set -eu
for name in industrial_review_plc industrial_review_hmi; do
    if jls -j "$name" >/dev/null 2>&1; then
        echo "Refusing to replace existing jail $name" >&2
        exit 1
    fi
done
plc_if=
hmi_if=
server_pid=
cleanup()
{
    jail -r industrial_review_plc 2>/dev/null || true
    jail -r industrial_review_hmi 2>/dev/null || true
    test -z "$plc_if" || ifconfig "$plc_if" destroy 2>/dev/null || true
    test -z "$hmi_if" || ifconfig "$hmi_if" destroy 2>/dev/null || true
    /sbin/pfctl -k 198.18.230.0/24 >/dev/null 2>&1 || true
    /sbin/pfctl -k 198.18.231.0/24 >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
test "$(sysctl -n net.inet.ip.forwarding)" = 1
plc_if=$(ifconfig epair create)
hmi_if=$(ifconfig epair create)
jail -c name=industrial_review_plc host.hostname=industrial-review-plc path=/ persist vnet allow.raw_sockets=1
jail -c name=industrial_review_hmi host.hostname=industrial-review-hmi path=/ persist vnet allow.raw_sockets=1
ifconfig "${plc_if%a}b" vnet industrial_review_plc
ifconfig "${hmi_if%a}b" vnet industrial_review_hmi
ifconfig "$plc_if" inet 198.18.230.1/24 up
ifconfig "$hmi_if" inet 198.18.231.1/24 up
jexec industrial_review_plc ifconfig lo0 inet 127.0.0.1 up
jexec industrial_review_hmi ifconfig lo0 inet 127.0.0.1 up
jexec industrial_review_plc ifconfig "${plc_if%a}b" inet 198.18.230.10/24 up
jexec industrial_review_hmi ifconfig "${hmi_if%a}b" inet 198.18.231.10/24 up
jexec industrial_review_plc route add default 198.18.230.1
jexec industrial_review_hmi route add default 198.18.231.1
jexec industrial_review_plc /usr/local/bin/python3 -c '
import socket,threading,time
def listen(port):
 s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("0.0.0.0",port));s.listen()
 while True:
  c,_=s.accept();c.sendall(b"industrial-review-ok");c.close()
for port in (502,503):threading.Thread(target=listen,args=(port,),daemon=True).start()
time.sleep(40)
' >/tmp/industrial-review-plc.log 2>&1 &
server_pid=$!
sleep 1
jexec industrial_review_hmi /usr/local/bin/python3 -c '
import socket
with socket.create_connection(("198.18.230.10",502),timeout=4) as c:
 assert c.recv(64)==b"industrial-review-ok"
print("PASS: permitted HMI -> PLC TCP/502 traverses the gateway")
try:
 socket.create_connection(("198.18.230.10",503),timeout=2)
except TimeoutError:
 print("PASS: non-whitelisted TCP/503 is blocked by the gateway")
else:
 raise SystemExit("FAIL: TCP/503 unexpectedly allowed")
'
