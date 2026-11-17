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

**Go.** Numbers on the first 69% of the dump (2.0 of 2.7 million issues; the archive interleaves instances, so
the rest adds more of the same ones and the few not yet reached). They will be replaced by the full run before
this is merged.

| As of | usable releases | informative (10–90% slipped) | instances with ≥ 10 | usable on started issues alone |
|---|---|---|---|---|
| 14 days before | 1,888 | 1,153 | 8 | 327 |
| 28 days before | 1,795 | 1,231 | 8 | 269 |

14 days before release (instances with at least 10 usable releases):

| instance | releases | labelled issues | slipped | moved out | late, left out | started | started slipped | years |
|---|---|---|---|---|---|---|---|---|
| Red Hat | 948 | 55,754 | 81% | 65% | 1,977 | 11,180 | 60% | 2005–2021 |
| Apache | 326 | 22,806 | 90% | 62% | 524 | 1,784 | 70% | 2005–2021 |
| Jira | 168 | 7,180 | 62% | 43% | 515 | 1,950 | 25% | 2003–2021 |
| Spring | 149 | 6,154 | 65% | 52% | 220 | 707 | 46% | 2005–2018 |
| Qt | 116 | 6,003 | 87% | 56% | 397 | 2,575 | 80% | 2009–2021 |
| MongoDB | 107 | 6,170 | 65% | 61% | 165 | 1,534 | 43% | 2009–2021 |
| Jira Ecosystem | 50 | 1,822 | 46% | 40% | 272 | 262 | 10% | 2008–2016 |
| Sakai | 16 | 777 | 54% | 22% | 300 | 321 | 34% | 2005–2013 |

Every issue read so far but 7 has its full changelog.

## What this means for the benchmark

- **Most scheduled issues slip, mostly by being moved out.** Two weeks before a release, 46–90% of the
  still-open issues do not make it, and most of those were taken out of the release: a planning decision the
  changelog records, which makes it a clean label. "Everything slips" is a strong baseline on accuracy, so the
  benchmark reports PR-AUC and per-release ranking instead, and also the reverse question ("which issues will
  make it?").
- **Backlog inflates the rate.** Issues that only carried a version slip far more often than started ones (Jira
  62% against 25%, MongoDB 65% against 43%). The started set is reported next to the full one, so a model cannot
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
