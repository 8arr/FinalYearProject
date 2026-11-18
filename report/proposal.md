# Improving Bus Arrival Time Predictions on the 41C in Swords

Project Proposal

Miron Nekrasovs, C22486382, TU856 Computer Science

Supervisor: [supervisor name]

[date]

Anything in square brackets is something I still have to fill in or check before submitting.

---

## 1. Introduction

The TFI app and the real time displays at bus stops tell passengers when the next bus is due. These times are not always right. A bus can show as due for several minutes and then not turn up, or it can disappear from the list early. I take the 41C from the Boroimhe Laurels stop (stop 5029) in Swords, Co. Dublin, so the problem is one I run into myself.

This project asks whether the arrival times published by TFI can be made more accurate by combining them with information available at the same time: time of day, day of the week, weather, the live position of the bus and, later, traffic and ratings from passengers. The focus is on predictions made 30 or 60 minutes ahead, which is when someone decides whether to leave the house or wait.

A second concern is reliability of the tool itself. If it only works when TFI works, it is not much use at the moment it is most needed, so it is designed to keep giving an estimate when TFI is unavailable or returns bad data.

## 2. Aims and Objectives

**Aim.** To build and evaluate a system that predicts bus arrival times for the 41C more accurately than the times published by TFI, at prediction horizons of 30 and 60 minutes.

**Research questions.**

1. How much does TFI's predicted arrival time differ from the actual arrival time at 30 and 60 minutes ahead?
2. Can a model using time of day, weather and the live bus position reduce that difference, and by how much?
3. Do passenger ratings improve predictions, or are they noise?

**Objectives.**

1. Continuously collect TFI predictions, bus positions and weather for stop 5029 and five nearby stops on the 41C.
2. Work out actual arrival times from the collected data, using two methods, and compare them.
3. Build a prediction model and an evaluation that can say honestly whether it beats TFI.
4. Keep giving an estimate when TFI is down, using stored history.
5. Test the whole chain automatically, with a human check alongside, and deploy only when the tests pass.
6. Add traffic and passenger ratings and test whether each one helps.

## 3. Background and Related Work

### 3.1 Existing apps

The TFI Live app and the stop displays show predicted times from the National Transport Authority (NTA) real time system. Google Maps, Citymapper, Moovit and Transit also show real time arrivals for Dublin where they can access the feed. As far as I have seen, none of them show how reliable the predictions have been in the past. [Check properly and add what I find.]

### 3.2 Prediction methods

Published work on bus arrival time prediction includes historical averages, regression, tree based methods such as random forests and gradient boosting, neural networks (mainly LSTMs) and Kalman filters. [Add 5 to 10 papers with a sentence on each once I have read them.] Most work predicts journey time from scratch. Here a prediction from the transport authority already exists, so I treat the problem as learning how TFI's error depends on conditions, and correcting for it.

### 3.3 Technology alternatives

| Part | Options considered | Choice and reason |
| --- | --- | --- |
| Data source | NTA GTFS-Realtime API; older per stop real time web services; scraping the TFI site or app | NTA GTFS-R. It is official, free with a key and gives predictions and vehicle positions for all buses in one request. Scraping is fragile and may breach the terms of use. |
| Prediction | Timetable or historical average; linear or ridge regression; gradient boosting; LSTM; Kalman filter | Gradient boosting. It works on small tabular data and can be explained. LSTMs need much more data than will be available and Kalman filters need positions along the whole route. |
| Storage | SQLite; PostgreSQL; time series databases; CSV or Parquet | SQLite. One file, no server to run, easy to back up and copy. PostgreSQL is a sensible move if more than one writer is needed. |
| Hosting | Google Compute Engine; AWS or Azure; Raspberry Pi at home; university server | Google Compute Engine e2-micro. Always on and mostly covered by the free tier, with a few dollars a month for the public IP address. A home Pi would depend on my internet and power. |
| Weather | Open-Meteo; Met Eireann open data; other weather APIs | Open-Meteo. Free, no key needed. |
| Traffic | Google Maps, TomTom or HERE APIs; the buses' own speeds | Likely the buses' own speeds first, as it costs nothing. [Check current prices of the paid APIs.] |
| Language and tools | Python or R; scikit-learn or XGBoost or neural network libraries; pytest; GitHub Actions | Python with scikit-learn and pytest, because one language covers the collector, analysis and tests. GitHub Actions runs the tests on every push. |

## 4. Proposed Approach

**Collection.** A Python service on the cloud server polls the NTA API once a minute for trip updates and vehicle positions, and weather every ten minutes, and keeps only the 41C buses and the six chosen stops (5029, 5031, 5030, 5028, 6033 and 6015). One request returns every bus in the country, so two requests a minute are enough and the polling rate should not be a problem for the API. Every request is logged so gaps can be explained later. The service restarts itself after a crash and the database is backed up every night.

**Actual arrival times.** The feed gives predictions, not confirmed arrivals, so two methods are used to reconstruct them. In the GPS method the bus path is interpolated between positions, and the arrival is the time it was closest to the stop, provided that was within 25 metres. This is needed because a bus moves several hundred metres between polls. In the feed method the arrival is taken as one minute before the stop disappeared from TFI's list. The two are compared, which is a useful result on its own.

**Prediction.** For each arrival, the system takes the moment TFI said the bus was 30 (or 60) minutes away, and records TFI's predicted time along with hour of day, weekend or not, rain and wind. A gradient boosting model learns the correction to apply to TFI's time. If there is nothing to learn the correction tends to zero, so the model stays close to TFI. The choice of moment is based on what TFI said, not on when the bus really arrived, to avoid leaking the answer into the inputs.

**When TFI fails.** The live feed is checked before use (not empty, not stale, plausible times and delays). If it fails the checks or is unreachable, the system uses past arrivals of the same kind of day (weekday, Saturday, Sunday) over the last four weeks and gives the typical time of the next timetable slots, marked as coming from history.

## 5. Testing and Evaluation

**Tests with known answers.** A simulator produces buses whose true arrival times are known, so the tests can check both positive and negative cases: a bus passing the stop is found, one passing 100 m away is not; a model beats TFI when delays depend on time of day and rain, and is not credited when they are pure noise; bad feeds are rejected; an estimate is still given when TFI is down.

**System test and pipeline.** A fake TFI server is run against the real collector, database, arrival detection and live estimate, one after the other. A single command runs every stage in order and stops at the first failure: unit tests, quality of stored data, a check of the live feed, arrival detection, accuracy against TFI, the fallback and the human review score. A problem found in the live feed is reported as a TFI fault, not as a failure of the project. The tests run on GitHub for every push. Deployment only happens when the pipeline passes on real data.

**Human check.** A local web page shows one bus at a time, with its distance from the stop over time, the detected arrival, and what TFI and the model predicted. I mark whether the detected arrival looks right. The pipeline fails if my agreement drops below 80 percent.

**Accuracy.** Models are trained on earlier days and tested on later ones. Measures are mean and median absolute error, root mean squared error, bias, and the share of predictions within one and two minutes. A paired bootstrap gives a 95 percent interval for the seconds saved per bus compared with TFI, and the model is only called better if the whole interval is above zero. The same approach tests each input (time of day, weather and later traffic and ratings): it is kept only if removing it makes the error on unseen days worse.

**Early results.** On simulated data the tools find a real effect when one exists and report nothing when there is none. For example, the GPS method recovered simulated arrival times with an average error of 0.4 seconds, and the model's saving over TFI was clearly above zero with effects present and inconclusive without. Results on real data will be reported in the interim report. [Add one line on real data here if it is available by then.]

## 6. Plan, Risks and Ethics

| Period | Work |
| --- | --- |
| [dates] | Run the full pipeline on real data, review cases by hand |
| [dates] | Add traffic and test whether it helps |
| [dates] | Collect passenger ratings and test whether they help |
| [dates] | Try other models if needed and compare |
| [dates] | Deploy with the fallback |
| [dates] | Final report and demo |

**Risks.** The main ones are too little data (mitigated by keeping the collector running and reporting confidence intervals), gaps in collection (logged and reported, backed up nightly), TFI changing its identifiers (health checks would show it quickly), and wrong ground truth (two methods plus the manual review). Results from a single stop may not hold elsewhere, and I will say so.

**Ethics and data.** The data collected so far is public transport data and weather, with no personal information. Passenger ratings would involve people, so I will check what TU Dublin requires for ethics approval and consent before collecting any, and keep them anonymous. I will follow the NTA open data licence and credit the source. [Check licence wording.]

## References

1. GTFS Realtime specification. https://gtfs.org/realtime/
2. National Transport Authority developer portal. https://developer.nationaltransport.ie
3. Open-Meteo weather API. https://open-meteo.com
4. Pedregosa, F. et al. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825 to 2830.
5. Friedman, J. H. (2001). Greedy function approximation: a gradient boosting machine. Annals of Statistics, 29(5), 1189 to 1232.
6. Efron, B. (1979). Bootstrap methods: another look at the jackknife. Annals of Statistics, 7(1), 1 to 26.
7. [Papers on bus arrival time prediction, to be added after reading]
