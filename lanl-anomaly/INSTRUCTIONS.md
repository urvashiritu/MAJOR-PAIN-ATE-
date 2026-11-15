# Project Instructions

This guide covers downloading, running, and demonstrating the LANL anomaly monitoring project.

## 1. Clone the project

Clone the branch containing the dashboard and SSH feature:

```bash
git clone -b final-updates https://github.com/urvashiritu/MAJOR-PAIN-ATE-.git
cd MAJOR-PAIN-ATE-/lanl-anomaly
```

## 2. Install and prepare the data

The project uses Python 3.12 or later, Git LFS, and zstd. On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install git-lfs zstd
git lfs install
```

Copy `lanl.duckdb.zst` (about 5.6 GB) into `data/raw/lanl/`. The database is not in GitHub. Then run:

```bash
./bootstrap.sh
```

Bootstrap installs the Python packages, pulls the models and processed data with Git LFS, decompresses the database, and checks the setup. See [SETUP.md](SETUP.md) for database transfer details.

## 3. Run the dashboard

```bash
LANL_DEV=1 venv/bin/python -m live.app
```

Open [http://localhost:5000](http://localhost:5000). Press `Ctrl+C` in the terminal to stop the app. `LANL_DEV=1` enables development login shortcuts; use it only on a trusted demo machine and do not expose the app to the public internet.

## 4. Demo the dashboard

- **Historical Events:** replay previously recorded LANL events and their labels.
- **Company demo:** open [http://localhost:5000/company](http://localhost:5000/company), submit a sign-in, then view it in **Live Monitoring**. The app shows the model score separately from the profile-deviation score. A changed value can flag a sign-in even if its model score is low. Open the flagged user's profile to see the detailed reason; an analyst can choose to block the user there.
- **Live Monitoring:** open the dashboard's Live Monitoring page to see company sign-ins and the separate SSH event table.

The company site is a demo. Its sign-in form does not connect to a real company or network.

## 5. Enable live SSH monitoring (Linux)

Run these steps on the Linux machine whose SSH logins you want to observe. Install the audit and SSH server tools:

```bash
sudo apt install auditd acl openssh-server
sudo systemctl enable --now auditd
sudo auditctl -e 1
sudo auditctl -s
sudo systemctl enable --now sshd || sudo systemctl enable --now ssh
```

The normal account running Flask needs read access to the audit log. Grant access to that account only; do not run the Flask server as root:

```bash
app_user=$(id -un)
sudo setfacl -m "u:${app_user}:x" /var/log/audit
sudo setfacl -m "u:${app_user}:r" /var/log/audit/audit.log /etc/audit/auditd.conf
```

Try an SSH sign-in to the same machine:

```bash
ssh "$USER"@localhost
```

For a second computer, connect to the monitored machine's IP address instead. View events in **Live Monitoring > Live SSH Authentication**. The SSH feed uses Linux Audit `USER_AUTH` records; it is separate from the LANL model. The display marks brute force after five failed authentication records from one IP within five minutes. This is a rule-based label, not a model verdict.

If the table reports `needs privilege`, check that the Flask account can read both `/etc/audit/auditd.conf` and `/var/log/audit/audit.log`. Log rotation may require restoring the log-file ACL.

## 6. Push future documentation changes

From the repository root, stage this file, commit it, and push the branch:

```bash
git add lanl-anomaly/INSTRUCTIONS.md
git commit -m "Add project run instructions"
git push origin final-updates
```
