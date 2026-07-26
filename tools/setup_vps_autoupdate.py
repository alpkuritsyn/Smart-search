#!/usr/bin/env python3
import sys
import paramiko

HOST = "185.212.131.59"
USER = "root"
PASSWORD = "Alpk24!"
PORT = 22

SCRIPT_CONTENT = """#!/usr/bin/env bash
cd /opt/smart-search
git fetch origin main >/dev/null 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New commits found ($LOCAL -> $REMOTE). Resetting to origin/main and restarting..." >> /var/log/smart-search-git-pull.log
    git reset --hard origin/main >> /var/log/smart-search-git-pull.log 2>&1
    systemctl restart smart-search >> /var/log/smart-search-git-pull.log 2>&1
fi
"""

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}...")
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    sftp = ssh.open_sftp()
    with sftp.file("/opt/smart-search/sync_and_restart.sh", "w") as f:
        f.write(SCRIPT_CONTENT)
    sftp.close()

    stdin, stdout, stderr = ssh.exec_command("chmod +x /opt/smart-search/sync_and_restart.sh && cd /opt/smart-search && git reset --hard origin/main && systemctl restart smart-search && systemctl status smart-search")
    print("STDOUT:\n" + stdout.read().decode("utf-8", errors="ignore"))
    print("STDERR:\n" + stderr.read().decode("utf-8", errors="ignore"))

    ssh.close()

if __name__ == "__main__":
    main()
