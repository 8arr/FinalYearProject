# Project Plan (draft)

Dates are my best guess. Check them against the official deadlines for the proposal, the interim report, the demo and the final submission, and move things around where they differ. The final submission date is assumed to be near the end of March 2027.

![Project plan](gantt.png)

## Done so far

| Task | When | Notes |
| --- | --- | --- |
| Topic choice and supervisor meetings | mid October to 9 Nov | |
| Stop selection, API key, cloud server setup | 9 to 11 Nov | 6 stops on the 41C around stop 5029 |
| Collector running, nightly backups | 10 to 12 Nov | only the evening of 11 Nov was stored correctly, 6 days lost |
| Arrival detection, model, fallback, tests, review page | 12 to 18 Nov | 81 tests, pipeline script, GitHub checks |
| Look at first real data, find and fix collector fault | 18 Nov | The collector had stored nothing since 12 Nov because TFI changed its route id format. Also found: the feed has delays but no clock times, the feed method for arrival times is unreliable, and about 22% of vehicle requests were rejected. All handled in code. |
| Draft proposal and interim report | 17 to 18 Nov | drafts to be rewritten by me |

## Still to do

| Task | Start | End | Length | Why this long |
| --- | --- | --- | --- | --- |
| Redeploy fixed collector, load timetable | 18 Nov | 23 Nov | a few days | The fix is written, it needs merging and restarting on the server, plus loading the timetable once. Do this first, every day of delay is a day of lost data. |
| Data collection (continuous, restarted) | 22 Nov | 5 Mar | about 15 weeks | Runs by itself. Check `scripts/status.py` every few days. Stop a week or two before the final evaluation so the numbers can be frozen. |
| Run pipeline on new data, fix problems | 1 Dec | 12 Dec | 2 weeks | Needs about 10 days of data to be meaningful. Real data has already found several problems, expect more. |
| Rewrite and send proposal | 19 Nov | 26 Nov | 1 week | The text exists already, the work is checking facts and rewriting in my own words. It is overdue so this goes first. |
| Check 50+ cases by hand | 7 Dec | 14 Dec | 1 week | About 2 minutes a case, spread over a few sittings. |
| Finish interim report | 23 Nov | 14 Dec | about 3 weeks | Needs the real results from the line above, so it runs alongside. Check the real deadline. |
| Interim demo preparation | 10 Dec | 17 Dec | 1 week | Short demo with the latest version. No slides beyond what is needed. |
| Ratings: form design and ethics check | 7 Dec | 9 Jan | 4 weeks elapsed, a few days of effort | Ethics approval can take weeks, so start early. |
| Traffic input (bus speeds first) | 14 Dec | 9 Jan | 3 weeks, slowed by holidays | Compute average bus speed near the stops from stored positions, test it as another input. A paid traffic API is only worth it if this shows promise. |
| Holidays, reduced work | 21 Dec | 4 Jan | 2 weeks | Check exam dates too and adjust. |
| Model improvements and comparisons | 11 Jan | 6 Feb | 4 weeks | Tune the model, compare with simpler and more complex ones, check each stop and each horizon. |
| Ratings collection | 11 Jan | 13 Feb | 5 weeks | Needs time to get enough responses. Realistically a few dozen to a couple of hundred. |
| Deployment of the estimate service | 8 Feb | 27 Feb | 3 weeks | A simple page or command that gives the next estimate with the TFI fallback, running on the same server. Only after the pipeline passes on real data. |
| Ratings analysis | 15 Feb | 27 Feb | 2 weeks | Test whether ratings help (keep) or are noise (drop). |
| Final evaluation on all data | 22 Feb | 6 Mar | 2 weeks | Freeze the data, rerun everything, produce the final tables and charts. |
| Final report writing | 11 Jan | 13 Mar | 9 weeks, low intensity | Write chapters as results arrive (background and design first, results last). |
| Code clean up and documentation | 1 Mar | 13 Mar | 2 weeks | Readable code, short README, tests still passing. |
| Buffer | 15 Mar | 27 Mar | 2 weeks | For things running late. |

## If time runs short

Cut in this order: passenger ratings (report it as future work and keep the method), then other models (keep just the one), then the paid traffic option. The collection, the comparison against TFI, the fallback and the testing are the core and should not be cut.

## Milestones to keep an eye on

- Proposal sent to supervisor: end of November
- Collector redeployed and storing data again: by 23 November
- First real results on the new data (even if the model does not beat TFI): around 12 December
- Interim report and demo: [check deadline], planned for mid December. The interim results will rest on only 2 to 3 weeks of data, so say so.
- Ratings ethics approval in place: early January
- Freeze data and rerun the evaluation: early March
- Final submission: [check deadline], planned for late March
