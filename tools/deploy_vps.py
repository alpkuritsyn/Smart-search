#!/usr/bin/env python3
import sys
import time
import json
import urllib.request
import paramiko

HOST = "185.212.131.59"
USER = "root"
PASSWORD = "Alpk24!"
PORT = 22

def run_remote(ssh, cmd):
    print(f"\n--- Executing: {cmd} ---")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    if out:
        print("STDOUT:\n" + out.strip())
    if err:
        print("STDERR:\n" + err.strip())
    return out, err

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}...")
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    # 1. Reset to latest GitHub main
    run_remote(ssh, "cd /opt/smart-search && git fetch origin && git reset --hard origin/main")

    # 2. Run taxonomy expansion on VPS to update canonical catalog & aliases
    run_remote(ssh, "cd /opt/smart-search && PYTHONUTF8=1 .venv/bin/python tools/expand_full_catalog_taxonomy.py")

    # 3. Kill old python serve_demo.py process
    run_remote(ssh, "pkill -9 -f 'serve_demo.py' || true")
    time.sleep(2)

    # 4. Start fresh server in background
    run_remote(ssh, "nohup /opt/smart-search/.venv/bin/python /opt/smart-search/tools/serve_demo.py --host 0.0.0.0 --port 8000 > /opt/smart-search/server.log 2>&1 &")
    time.sleep(3)

    # 5. Check running process
    run_remote(ssh, "ps aux | grep serve_demo.py | grep -v grep")
    run_remote(ssh, "head -n 20 /opt/smart-search/server.log")

    ssh.close()

    # 6. Verify HTTP response from production VPS
    print("\n--- Verifying Live Production HTTP API (http://185.212.131.59:8000) ---")
    time.sleep(3)
    for q in ["краска тикурила", "краска", "строганный брус"]:
        try:
            url = f"http://185.212.131.59:8000/api/search?q={urllib.parse.quote(q)}"
            req = urllib.request.urlopen(url, timeout=10)
            res = json.loads(req.read().decode('utf-8'))
            print(f"\nQuery: '{q}' | Strategy: {res.get('meta', {}).get('strategy')} | Title: {res.get('primary', {}).get('title')}")
            for i, p in enumerate(res.get("primary", {}).get("products", [])[:3]):
                print(f"  {i+1}. {p.get('name')} | Brand: {p.get('brand')} | Category: {p.get('category')}")
        except Exception as e:
            print(f"Verification Error for '{q}': {e}")

if __name__ == "__main__":
    main()
