# Running the collector on Google Cloud

The collector is tiny (a few requests a minute, a few MB of data a day) so the smallest VM is enough.

## 1. NTA API key

1. Register at https://developer.nationaltransport.ie
2. Go to Products, subscribe to the GTFS-R product
3. Copy the primary key from your profile page. This is `NTA_API_KEY`.

Quick check that the key works:

```
curl -s -o /dev/null -w "%{http_code}\n" -H "x-api-key: YOUR_KEY" https://api.nationaltransport.ie/gtfsr/v2/TripUpdates
```

200 means it is fine. While you are on the portal check the rate limit for the product. This setup makes 2 requests a minute (about 2900 a day), and it only needs those two because each response covers every bus in the country and we filter it ourselves. There is no need to query once per stop.

## 2. Google Cloud account

1. Go to https://console.cloud.google.com and sign in with a Google account
2. Accept the terms and activate the free trial if offered. It needs a card for identity checks, and you get some free credit. It will not charge you without you upgrading.
3. Create a project (top bar, project picker, New Project). Call it something like `fyp-bus`.
4. Make sure billing is linked to the project (Billing menu).

## 3. Create the VM

In the console go to Compute Engine, VM instances, Create instance (the Compute Engine API will enable itself the first time).

- Name: `bus-collector`
- Region: `us-central1` (the always free e2-micro is only available in us-west1, us-central1 and us-east1. The location does not matter for this job). If the NTA API refuses requests from the US, use `europe-west1` with an `e2-small` instead, which costs a few euro a month.
- Machine type: `e2-micro`
- Boot disk: Ubuntu 24.04 LTS, standard persistent disk, 20GB
- Leave the firewall boxes unticked, nothing needs to reach the VM

Then click Create. Using the command line instead, after installing the gcloud CLI and running `gcloud auth login`:

```
gcloud config set project YOUR_PROJECT_ID
gcloud compute instances create bus-collector \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB --boot-disk-type=pd-standard
```

## 4. Set up the VM

Click SSH next to the instance in the console (or `gcloud compute ssh bus-collector --zone=us-central1-a`), then:

```
sudo apt update && sudo apt install -y git python3-venv python3-pip
git clone https://github.com/8arr/FinalYearProject.git
cd FinalYearProject
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "NTA_API_KEY=YOUR_KEY" > .env
chmod 600 .env
```

If the repo is private, use a personal access token in the clone URL or set up a deploy key.

Try it in the foreground first for a minute:

```
set -a; . ./.env; set +a
.venv/bin/python -m collector.run
```

You should see lines like `trip updates: 2 rows from 600 entities`. Zero rows is normal when no bus is near the stops. Ctrl+C to stop.

## 5. Keep it running

The systemd unit restarts the collector if it crashes and starts it on boot. The unit file assumes the user `ubuntu`, so swap in your own username:

```
sed "s/ubuntu/$USER/g" deploy/bus-collector.service | sudo tee /etc/systemd/system/bus-collector.service
sudo systemctl daemon-reload
sudo systemctl enable --now bus-collector
```

Check on it:

```
systemctl status bus-collector
journalctl -u bus-collector -f
.venv/bin/python scripts/status.py
```

To update after pushing code changes: `git pull && sudo systemctl restart bus-collector`.

## 6. Backups

The database is a single file at `data/bus.db`. Copy it to your own machine now and then:

```
gcloud compute scp bus-collector:~/FinalYearProject/data/bus.db . --zone=us-central1-a
```

It is safe to copy while the collector is running because SQLite is in WAL mode, but grab the `-wal` file too, or stop the service briefly first. A disk snapshot (Compute Engine, Snapshots) is also an easy extra backup.

## Costs

The console price estimate when creating the VM (about $8 a month) is the normal list price and does not take the free tier into account. The free tier is taken off your bill afterwards.

It covers one e2-micro per month in us-west1, us-central1 or us-east1, plus 30GB of standard persistent disk (not balanced or SSD, so change the disk type when creating the VM). It does not cover the external IPv4 address, which is a few dollars a month. While the free trial credit lasts that is paid from the credit.

Set a budget alert (Billing, Budgets and alerts) at a few euro so you get an email if the bill is higher than expected, and check Billing, Reports after a few days to see what is actually being charged.
