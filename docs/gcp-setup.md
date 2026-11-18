# Running the collector on Google Cloud

The collector makes 2 requests a minute and stores a few MB a day, so an e2-micro is plenty.

## NTA key

Register at https://developer.nationaltransport.ie, subscribe to the GTFS-R product and copy the primary key. Check it:

```
curl -s -o /dev/null -w "%{http_code}\n" -H "x-api-key: YOUR_KEY" https://api.nationaltransport.ie/gtfsr/v2/TripUpdates
```

200 means it works.

## The VM

Create a project in the Google Cloud console and link billing (the free trial needs a card). Then Compute Engine, create instance:

- name `bus-collector`, region `us-central1` (free tier is only us-west1, us-central1, us-east1)
- machine type `e2-micro`
- Ubuntu 24.04 LTS, standard persistent disk (not balanced), 20GB
- leave the firewall boxes unticked

The ~$8 estimate in the console ignores the free tier, it comes off the bill later. The external IP is not free though, a few dollars a month. Set a budget alert at a few euro.

## Setting it up

SSH in from the console and run:

```
sudo apt update && sudo apt install -y git python3-venv python3-pip sqlite3
git clone https://github.com/8arr/FinalYearProject.git
cd FinalYearProject
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "NTA_API_KEY=YOUR_KEY" > .env
chmod 600 .env
.venv/bin/python scripts/load_schedule.py
```

Try it in the foreground first (Ctrl+C to stop):

```
set -a; . ./.env; set +a
.venv/bin/python -m collector.run
```

## Keeping it running

The unit file uses the user `ubuntu`, so swap in yours:

```
sed "s/ubuntu/$USER/g" deploy/bus-collector.service | sudo tee /etc/systemd/system/bus-collector.service
sudo systemctl daemon-reload
sudo systemctl enable --now bus-collector
```

Check with `systemctl status bus-collector`, `journalctl -u bus-collector -f` and `.venv/bin/python scripts/status.py`. After pushing changes: `git pull && sudo systemctl restart bus-collector`.

If `status.py` shows 0 rows in the last 24h, the route id or stops have probably changed (it went from `1 41C c a` to `1_41C_c_a` once). Rerun:

```
.venv/bin/python scripts/find_stops.py --main 5029 --routes 41C --count 6
.venv/bin/python scripts/load_schedule.py
sudo systemctl restart bus-collector
```

## Backups to OneDrive

`scripts/backup.sh` makes a copy with sqlite3 `.backup` (safe while the collector is writing), gzips it and uploads it with rclone.

```
curl https://rclone.org/install.sh | sudo bash
```

The VM has no browser, so on my PC I ran `rclone authorize "onedrive"`, signed in, and copied the token it printed. Then on the VM `rclone config`: new remote called `onedrive`, type `onedrive`, leave client id and secret blank, region 1, no advanced config, say no to the web browser question and paste the token, then pick the personal drive.

Test it:

```
rclone lsd onedrive:
./scripts/backup.sh
rclone ls onedrive:fyp-backups
```

Then `crontab -e` and add (3am every night):

```
0 3 * * * /home/YOUR_USERNAME/FinalYearProject/scripts/backup.sh >> /tmp/backup.log 2>&1
```
