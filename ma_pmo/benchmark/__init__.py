"""Benchmark on public Jira history (roadmap 3).

    ma-pmo benchmark coverage <dump>

The data is the Public Jira Dataset (Montgomery, Lüders, Maalej, MSR 2022), a `mongodump --gzip
--archive` of 16 public Jira instances. It is read as a stream (`dump`), each issue's fix-version
history is replayed to an as-of date (`history`), and `coverage` says whether there are enough
releases to benchmark on. The data is never committed; see docs/BENCHMARK.md.
"""
