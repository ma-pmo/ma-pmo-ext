# Benchmark on public Jira history

**English | [한국어](BENCHMARK.ko.md)**

H1–H5 are measured on three demo projects, which our own [validation guide](PAPER_VALIDATION_GUIDE.md) lists as
the main threat to validity. Roadmap 3 ([#38](https://github.com/ma-pmo/ma-pmo-ext/issues/38)) replays real
release history from public Jira instances so the risk and schedule agents can be scored against what actually
happened. This page covers the first step: is there enough history to do that?

## Data

The [Public Jira Dataset](https://arxiv.org/abs/2201.08368) (Montgomery, Lüders, Maalej, MSR 2022), the
anonymised 2025-06-23 version on [Zenodo](https://zenodo.org/records/15719919), CC BY 4.0: 16 public Jira
instances (Apache, Red Hat, Jira, Mojang, Spring, Qt, MariaDB, Hyperledger, MongoDB, Sakai, Second Life, JFrog,
Sonatype, Intel DAOS, Mindville, Jira Ecosystem) with every issue's fields and full changelog. It is one zip of
5.8 GB holding a `mongodump --gzip --archive` (about 60 GB in MongoDB).

The data is never committed to this repository. Download it yourself and check the hash:

```bash
curl -L -o ThePublicJiraDataset.zip \
  "https://zenodo.org/records/15719919/files/2025-06-23%20ThePublicJiraDataset.zip?download=1"
md5 ThePublicJiraDataset.zip        # 02f85309d966092ea130ca0797aea795
```

No MongoDB is needed: `ma_pmo.benchmark.dump` reads the archive inside the zip as a stream.

## Rules

- **Unit:** a release, i.e. a Jira fix version that is released and has a release date.
- **As-of date:** T = release date − k days (k = 14 and 28).
- **Scheduled at T:** the issue existed at T, was unresolved at T, and had the release as a fix version at T.
  An issue's fix versions at T are its current ones with every "Fix Version" change after T undone.
- **Outcome,** read one day after the release date (D):

  | outcome | at D | label |
  |---|---|---|
  | on time | resolved, release still a fix version | not slipped |
  | moved out | release no longer a fix version | slipped |
  | open | release still a fix version, unresolved, and never resolved with it afterwards | slipped |
  | late | release still a fix version, unresolved, resolved later with it kept | left out |

  *Late* is left out of the label: these issues are often closed after the release by QA or clean-up (in Jira's
  own tracker half of them within a week, in Apache's after months), so whether they made the release is unclear.
- **Started at T:** the issue's status at T (replayed like the fix versions) is not a not-started one such as
  Open, To Do or Backlog. Started issues are reported as a second set, without the backlog that only carried a
  version.
- **Usable release:** at least 20 labelled issues scheduled at T.
- **Bar to go ahead:** at least 200 usable releases, with at least 10 in each of at least 3 instances.

```bash
pip install "ma-pmo[benchmark]"
ma-pmo benchmark coverage ThePublicJiraDataset.zip            # Markdown
ma-pmo benchmark coverage ThePublicJiraDataset.zip --json     # all counters
```

## Spike result

**Go.** The full dump (md5 checked): 2,686,282 issues in 16 instances, all but 13 with their full
changelog. Reading it with `ma-pmo benchmark coverage` takes about two minutes.

| As of | usable releases | informative (10–90% slipped) | instances with ≥ 10 | usable on started issues alone |
|---|---|---|---|---|
| 14 days before | 2,367 | 1,430 | 11 | 330 |
| 28 days before | 2,429 | 1,703 | 11 | 302 |

14 days before release (instances with at least 10 usable releases):

| instance | releases | labelled issues | slipped | moved out | late, left out | started | started slipped | years |
|---|---|---|---|---|---|---|---|---|
| Red Hat | 904 | 53,130 | 81% | 66% | 921 | 8,942 | 59% | 2005–2021 |
| Apache | 770 | 47,795 | 85% | 65% | 669 | 5,365 | 70% | 2004–2021 |
| Jira | 166 | 7,076 | 62% | 43% | 455 | 1,865 | 22% | 2003–2021 |
| Spring | 144 | 5,969 | 64% | 53% | 123 | 545 | 40% | 2005–2018 |
| Qt | 108 | 5,673 | 88% | 58% | 268 | 2,304 | 80% | 2009–2021 |
| MongoDB | 107 | 6,052 | 66% | 62% | 111 | 1,407 | 44% | 2009–2021 |
| Jira Ecosystem | 50 | 1,823 | 46% | 40% | 242 | 257 | 10% | 2008–2016 |
| MariaDB | 49 | 4,709 | 86% | 76% | 23 | 670 | 64% | 2012–2020 |
| JFrog | 32 | 940 | 57% | 57% | 9 | 305 | 31% | 2008–2019 |
| Hyperledger | 11 | 904 | 74% | 14% | 483 | 447 | 64% | 2017–2020 |
| Sakai | 10 | 407 | 71% | 31% | 39 | 25 | 52% | 2005–2013 |

Mojang (420,819 issues) has almost no usable release: its fix versions are mostly set when an issue
is resolved, not planned ahead. Mindville has none at all.

## Replaying a release (step 2)

```bash
ma-pmo benchmark prepare ThePublicJiraDataset.zip --out bench-data   # once; never commit it
ma-pmo benchmark replay bench-data                                   # list the releases
ma-pmo benchmark replay bench-data Apache/12345678 --k 14            # one release at T
```

`prepare` keeps the usable releases and the full history of their issues (`releases.jsonl`,
`issues.jsonl.gz`, `manifest.json`). The **ReplayTracker** (`ma_pmo/benchmark/replay.py`) serves
them through the ordinary tracker contract, so the real agents run on a release as it stood at T:
one project per release, with the issues that had it as a fix version at T as tasks (progress 100
if resolved at T, 50 if started, else 0; the original estimate at T, else 8 hours; the issues of
the same release that blocked it at T as dependencies), the release date as deadline, and each
task's status, priority, assignee and type at T. Every value is the current one with the changes
after T undone; a test adds random changes after T to every issue (status, resolution, priority,
assignee, estimate, links, fix versions) and checks the tracker shows exactly the same.
Outcomes are only read for scoring (`ReplayTracker.outcomes`), never shown to agents. Agents that
store what they produce against a project (A4 keeps its alerts in the `risk` table) need the
project in the database, which a replay is not: the benchmark reads A4 through its signal
analysis (`a4_signals`), and a full agent run on replays needs a throwaway database.

## Scoring issues (step 3)

```bash
ma-pmo benchmark run bench-data              # Markdown; --json, --out results.json, --k 14 28
```

Every issue scheduled for a usable release at T is a row, labelled 1 if it slipped (moved out or
still open a day after the release) and 0 if it was resolved in time; late closures are left out.
"Unresolved at T" and "resolved by the release" are read from the resolution's own history, so an
issue resolved before T and reopened afterwards is not counted as open at T.

| scorer | what it sees at T |
|---|---|
| `all_slip` | nothing: every issue slips (the majority class) |
| `progress` | not started 1, started 0.5, in review 0.2 |
| `a4_signals` | A4's own rule signals on the replayed release, per task: blocked 0.9, stalled 0.7, else 0.3 |
| `forest` | a random forest on the issue-delay literature's features (`benchmark/features.py`): state, age, days since the last status change, reschedules so far, links, priority, type, assignee load, release size |

Releases are split by date: the earliest 70% train the forest; every scorer is measured on the
latest 30%. Metrics: PR-AUC with a 95% bootstrap interval over releases, ROC-AUC, F1 at 0.5, Brier,
ECE, and PR-AUC for the reverse question (which issues make it), on all issues, on informative
releases and on issues already started at T, plus PR-AUC per collection. A test adds random changes
after T to every issue and checks the features do not move.

Results on the full dump (`ma-pmo benchmark run`, test = the latest 711 releases at k = 14):

| scorer | all issues: PR-AUC [95% CI] | ROC-AUC | ECE | started issues: PR-AUC | ROC-AUC |
|---|---|---|---|---|---|
| all_slip | 0.829 [0.814, 0.843] | 0.5 | 0.171 | 0.620 | 0.5 |
| progress | 0.884 [0.869, 0.896] | 0.678 | 0.115 | 0.637 | 0.534 |
| a4_signals | 0.881 [0.866, 0.894] | 0.670 | 0.223 | 0.621 | 0.500 |
| forest | **0.964** [0.957, 0.970] | **0.858** | 0.039 | **0.869** | **0.793** |

At k = 28 the order is the same (forest PR-AUC 0.934, ROC-AUC 0.825; on started issues 0.846 and
0.804).

- **A4's rule signals add nothing over "not started yet"** (ROC-AUC 0.67 against 0.68), and on
  issues already started they are no better than chance: such an issue is never "stalled" (50%
  progress) and rarely blocked inside its release, so every one gets the same score.
- **The literature baseline is far ahead**, mostly through how long an issue has gone untouched
  (days since its last status change, ROC-AUC 0.84 on its own) and its age: old, idle issues are
  moved out. This is the bar an agent has to clear.
- **A4's scores are not calibrated** (ECE 0.22: a "0.9" slips far less than 90% of the time, a
  "0.3" far more). Roadmap 11 calibrates them on these labels.

## Calibrating A4 (roadmap 11)

```bash
ma-pmo benchmark calibrate bench-data --out my_calibration.json   # MA_PMO_A4_CALIBRATION reads it
```

A4 used to report confidence 0.85 for every alert. It now reports the chance that the tasks an
alert points at slip, from a table of what happened to issues with the same evidence in the
training releases (`ma_pmo/fixtures/a4_calibration.json`, `agents/risk_calibration.py`):

| A4's evidence on a task | issues (train) | slipped [95% CI] | slipped in the latest releases |
|---|---|---|---|
| blocked by an unfinished task | 927 | 0.740 [0.711, 0.767] | 0.773 |
| stalled (predecessors done, under 50%) | 80,360 | 0.819 [0.816, 0.822] | 0.894 |
| moving (anything else still open) | 12,359 | 0.564 [0.555, 0.573] | 0.620 |

On the latest 711 releases, ECE falls from 0.223 (the old fixed scores) to 0.070 and the Brier
score from 0.181 to 0.133. The remaining error is drift: later releases slip more than the
training ones. Two findings shaped the table: blocked tasks slip *less* often than stalled ones,
so the kinds are treated as categories rather than a scale, and the evidence separates issues
only modestly (ROC-AUC 0.67), so calibrated confidence makes A4's alerts honest, not sharp. On the
demo portfolio PROJ-14's alert now carries 0.74 and PROJ-31's 0.78.

### A review threshold with a guarantee

`HITL_CONFIDENCE_THRESHOLD` (0.6) says nothing about how many wrong alerts get through. With
`HITL_RISK_ALPHA` set, A4's alerts use a threshold chosen on the calibration table's held-out
releases instead (`core/risk_control.py`): the lowest confidence at which the alerts committed
without a person are wrong at most α of the time, with probability 1 − δ (`HITL_RISK_DELTA`,
default 0.1). Candidates are tested from the highest down and the first that fails stops the
search (fixed-sequence testing, as in Learn-then-Test), each against a one-sided Clopper–Pearson
bound. On the benchmark table:

| α | threshold | committed without a person |
|---|---|---|
| 0.15 | 0.74 | stalled and blocked evidence (10.7% wrong, 31,887 held-out issues) |
| 0.20 | 0.56 | everything (17.1% wrong) |

So with α = 0.15, an alert that rests only on tasks already moving (0.56) goes to a person, and
one that points at stalled or blocked tasks does not. Other agents keep the fixed threshold.

## What this means for the benchmark

- **Most scheduled issues slip, mostly by being moved out.** Two weeks before a release, 46–88% of the
  still-open issues do not make it, and most of those were taken out of the release: a planning decision the
  changelog records, which makes it a clean label. "Everything slips" is a strong baseline on accuracy, so the
  benchmark reports PR-AUC and per-release ranking instead, and also the reverse question ("which issues will
  make it?").
- **Backlog inflates the rate.** Issues that only carried a version slip far more often than started ones (Jira
  62% against 22%, MongoDB 66% against 44%). The started set is reported next to the full one, so a model cannot
  look good just by spotting untouched backlog.
- **Informative releases are the main set.** Releases where every issue (or none) slipped have little to tell
  apart; the 10–90% releases are the primary evaluation set.
- **This is prediction, not cause.** The history has no interventions, so the benchmark says whether a slip
  could have been seen coming at T, not whether an alert would have prevented it.
- **Limits.** `releaseDate` may be the actual rather than the planned date, and the changelog does not record
  changes to it, so an as-of date tied to it uses slightly later knowledge than a PM had. There is no capacity
  data, so H2 is out of scope here. Open-source projects are not a corporate PMO.

## Related work

- Choetkiertikul et al., [Predicting delays in software projects using networked
  classification](https://seanalytics.github.io/papers/ASE2015-preprint-choetkiertikul-dam-tran-ghose.pdf),
  ASE 2015, and [Predicting the delay of issues with due dates](https://dx.doi.org/10.1007/s10664-016-9496-7),
  EMSE 2017: issue-level delay prediction on Jira projects; the source of the literature baseline and link features.
- [Release readiness classification](https://old.ruhe.cpsc.ucalgary.ca/downloads/publications/conference/Release%20Readiness%20Classification.pdf):
  release-level readiness as binary classification.

Their numbers were not necessarily obtained with an as-of replay, so only results re-run on these rules are compared.
