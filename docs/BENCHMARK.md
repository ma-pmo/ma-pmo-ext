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
- **Slipped:** the release is no longer one of its fix versions, or it was not resolved by the release date
  plus one day.
- **Usable release:** at least 20 issues scheduled at T.
- **Bar to go ahead:** at least 200 usable releases, with at least 10 in each of at least 3 instances.

```bash
pip install "ma-pmo[benchmark]"
ma-pmo benchmark coverage ThePublicJiraDataset.zip            # Markdown
ma-pmo benchmark coverage ThePublicJiraDataset.zip --json     # all counters
```

## Spike result

**Go.** Interim numbers on the first 39% of the dump (the archive interleaves instances, so the rest adds more
of Apache and the instances not yet reached); they will be replaced by the full run before this is merged.

| As of | usable releases | informative (10–90% slipped) | instances with ≥ 10 |
|---|---|---|---|
| 14 days before | 1,098 | 654 | 3 |
| 28 days before | 1,033 | 699 | 3 |

14 days before release:

| instance | releases | issues | slipped | of which moved out | years |
|---|---|---|---|---|---|
| Red Hat | 782 | 48,779 | 82% | 76% | 2004–2021 |
| Apache | 190 | 13,813 | 92% | 79% | 2002–2021 |
| Jira | 125 | 5,814 | 70% | 61% | 2003–2021 |

Every issue read so far has its full changelog.

## What this means for the benchmark

- **Most scheduled issues slip.** Two weeks before a release, 70–92% of the still-open issues do not make it,
  mostly because projects move what is left to the next version when they release. "Everything slips" is
  therefore a strong baseline on accuracy, so the benchmark reports PR-AUC and per-release ranking instead, and
  also the reverse question ("which issues will make it?"), where the positive class is the minority.
- **Informative releases are the main set.** Releases where every issue (or none) slipped have little to tell
  apart; the 10–90% releases are the primary evaluation set.
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
