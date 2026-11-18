# Looking at the real data, step by step

Commands are for Windows PowerShell. On Mac or Linux the only differences are noted in step 3.

## A. Set up your computer (once)

1. Install Python 3.12 from python.org (tick "Add python.exe to PATH" in the installer) and Git. Check with `python --version` and `git --version`.
2. Open PowerShell in a folder like Documents and run:

   ```
   git clone https://github.com/8arr/FinalYearProject.git
   cd FinalYearProject
   git checkout prediction-tests
   ```

   If the branch has already been merged, use `git checkout main` and `git pull` instead.
3. Make a private Python environment and install what is needed:

   ```
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements-analysis.txt
   ```

   If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope Process Bypass` and try again. On Mac or Linux activate with `source .venv/bin/activate`. You should see `(.venv)` at the start of the prompt. You need to activate it every time you open a new window.
4. Check the install: `python -m pytest -q tests`. It should end with `65 passed`.

## B. Get the data

5. From OneDrive, open the `fyp-backups` folder and download the newest file, named like `bus-20261118-0300.db.gz`.
6. Unzip it with 7-Zip (right click, 7-Zip, Extract here). Rename the result to `bus.db` and put it in the repository's `data` folder. Check it with `dir data`, it should be several MB or more.

If you want data newer than last night's backup, run these on the VM, then download the copy:

```
cd ~/fyp/FinalYearProject
sqlite3 data/bus.db ".backup '/tmp/copy.db'"
```

and on your computer (with the gcloud tool installed):

```
gcloud compute scp bus-collector:/tmp/copy.db data/bus.db --zone=us-central1-a
```

## C. First look

7. Run:

   ```
   python scripts/data_overview.py data/bus.db
   ```

   What to look for:

   - **collected from / to**: the dates and number of days match what you expect (since 11 Nov).
   - **polls by feed**: both feeds mostly above 95% ok.
   - **trip_updates columns**: `arrival_time` and `arrival_delay` should be mostly filled. If `arrival_time` is mostly empty, stop and tell me, because the tests need it and I would change how TFI's predicted time is worked out.
   - **vehicle_positions columns**: `trip_id` and `position_time` should be mostly filled.
   - **arrival_delay in minutes**: a sensible spread, roughly a few minutes early to several minutes late. Values like 500 minutes mean bad data.
   - **per stop**: every stop should have some trips. A stop with none never showed up in the feed.
   - **per day**: no day with zero or a tiny number (that would be an outage).
8. Optional: install DB Browser for SQLite (sqlitebrowser.org), open `data/bus.db` read only and click through the tables in the Browse Data tab. Times are stored as UTC seconds. A query to try in the Execute SQL tab:

   ```
   SELECT datetime(polled_at, 'unixepoch') AS polled, stop_id, trip_id, arrival_delay
   FROM trip_updates ORDER BY polled_at DESC LIMIT 50;
   ```

## D. Run the checks

9. Run the whole pipeline (skipping the unit tests, which you just ran):

   ```
   python scripts/run_pipeline.py --skip-tests
   ```

   Reading the stages:

   - **stored data quality**: gaps and failed polls show as warnings. "last good poll was 20h ago" only means your copy is old.
   - **live feed check**: skipped unless your key is set. To include it: `$env:NTA_API_KEY="your key"` then run again with `--skip-tests`.
   - **arrival detection**: should find hundreds of arrivals. The median difference between the GPS and feed methods is a result for the report. If it says too few arrivals, send me the output of step 7.
   - **accuracy against TFI**: one line per horizon. "not enough data" at 60 minutes could mean the feed does not list buses that far ahead, which is useful to know.
   - **fallback**: needs at least a few days of history, and about three weeks before weekends have enough.
   - **human review**: skipped until you have reviewed some cases.
10. Get the accuracy tables:

    ```
    python -m bus.evaluate --horizon 30 60
    python -m bus.evaluate --horizon 30 60 --truth gps
    python -m bus.evaluate --horizon 30 60 --truth feed
    ```

    Compare the three: they show how much the answer depends on how the real arrival time is worked out. In each table, MAE is the average error in minutes (lower is better), and the `<=1min` columns are the share of predictions within a minute or two. The last lines say whether the model beat TFI and by how many seconds per bus.

## E. Check cases by eye

11. Run `python -m bus.review --horizon 30` and open http://127.0.0.1:8000 in your browser. Each page is one bus:

    - The grey line is the bus's distance from the stop. It should come down to the dashed 25 m line and the green marker (detected arrival) should sit at the lowest point.
    - Click **Looks right** if so. Click **Looks wrong** if the line never gets near the stop, the green marker is far from the lowest point, the track is mostly straight lines across a big gap, or it looks like a different bus. Add a short note when you click wrong, and write down the trip name shown at the top.
    - Skip if you cannot tell.

    Aim for about 25 cases at 30 minutes, then repeat with `--horizon 60`. Answers are saved as you go and Ctrl+C in the window stops the page. Run it again to carry on with unreviewed cases. Then run the pipeline again, and the last stage will show how often you agreed.

## F. What to send me

- The output of steps 7, 9 and 10, pasted as text
- The trip names of any "Looks wrong" cases and what looked wrong
- Or upload `bus.db.gz` straight to the chat (you do not need to unzip it). It contains no passwords or keys.

Never send your NTA API key.

## Common problems

| Message | What it means |
| --- | --- |
| `No module named ...` | The environment is not active. Run the activate command from step 3. |
| `no such table` or `unable to open database file` | The file is not at `data/bus.db`, or the download was cut short. |
| `database is locked` | You are reading the live database on the VM. Use a copy as in step 6. |
| `FileNotFoundError: data/targets.json` | You are in the wrong folder, `cd` into FinalYearProject. |
| Pipeline says `SKIP` for most stages | There is not enough data for that stage yet. Collect more days. |
