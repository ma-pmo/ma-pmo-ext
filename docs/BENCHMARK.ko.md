# 공개 Jira 이력 벤치마크

**[English](BENCHMARK.md) | 한국어**

H1~H5는 데모 프로젝트 세 개로 측정합니다. 이것이 타당성의 가장 큰 위협이라고 우리 [검증 가이드](PAPER_VALIDATION_GUIDE.ko.md)에도
적혀 있습니다. 로드맵 3([#38](https://github.com/ma-pmo/ma-pmo-ext/issues/38))은 공개 Jira의 실제 릴리스 이력을
재생해, 리스크·일정 에이전트를 실제로 일어난 일과 대조합니다. 이 문서는 그 첫 단계인 "그럴 만큼 이력이 충분한가"를
다룹니다.

## 데이터

[Public Jira Dataset](https://arxiv.org/abs/2201.08368)(Montgomery, Lüders, Maalej, MSR 2022)의 익명화된 2025-06-23판
([Zenodo](https://zenodo.org/records/15719919), CC BY 4.0). 공개 Jira 16곳(Apache, Red Hat, Jira, Mojang, Spring, Qt,
MariaDB, Hyperledger, MongoDB, Sakai, Second Life, JFrog, Sonatype, Intel DAOS, Mindville, Jira Ecosystem)의 이슈 필드와
변경 이력 전체가 들어 있습니다. 5.8GB zip 하나에 `mongodump --gzip --archive` 파일이 있습니다(MongoDB에 풀면 약 60GB).

데이터는 이 저장소에 넣지 않습니다. 직접 받아 해시를 확인하세요.

```bash
curl -L -o ThePublicJiraDataset.zip \
  "https://zenodo.org/records/15719919/files/2025-06-23%20ThePublicJiraDataset.zip?download=1"
md5 ThePublicJiraDataset.zip        # 02f85309d966092ea130ca0797aea795
```

MongoDB는 필요 없습니다. `ma_pmo.benchmark.dump`가 zip 안의 아카이브를 스트림으로 읽습니다.

## 규칙

- **단위:** 릴리스. 출시되었고(released) 출시일이 있는 Jira fix version입니다.
- **시점:** T = 출시일 − k일(k = 14, 28).
- **T에 예정됨:** T에 이미 있었고, T에 미해결이었고, T에 그 릴리스가 fix version이었던 이슈. T의 fix version은 지금의
  fix version에서 T 이후의 "Fix Version" 변경을 모두 되돌린 것입니다.
- **결과:** 출시일 다음 날(D)에 봅니다.

  | 결과 | D 시점 | 레이블 |
  |---|---|---|
  | 제때 | 해결됨, 릴리스가 여전히 fix version | 안 밀림 |
  | 빠짐 | 릴리스가 더는 fix version이 아님 | 밀림 |
  | 미해결 | 릴리스가 fix version, 미해결, 이후에도 그 버전으로는 해결 안 됨 | 밀림 |
  | 늦음 | 릴리스가 fix version, 미해결, 나중에 버전을 유지한 채 해결 | 제외 |

  *늦음*은 레이블에서 뺍니다. 출시 뒤 QA나 정리 작업으로 닫는 경우가 많아(Jira 자체 트래커는 절반이 일주일 안,
  Apache는 몇 달 뒤) 릴리스에 들어갔는지 분명하지 않기 때문입니다.
- **T에 시작됨:** T 시점의 상태(fix version처럼 되돌려 구함)가 Open, To Do, Backlog 같은 시작 전 상태가 아님.
  시작된 이슈만 본 결과를 두 번째 집합으로 냅니다. 버전만 붙어 있던 백로그가 빠집니다.
- **쓸 수 있는 릴리스:** T에 예정되고 레이블이 있는 이슈가 20개 이상.
- **진행 기준:** 쓸 수 있는 릴리스 200개 이상, 그중 10개 이상인 인스턴스가 3곳 이상.

```bash
pip install "ma-pmo[benchmark]"
ma-pmo benchmark coverage ThePublicJiraDataset.zip            # Markdown
ma-pmo benchmark coverage ThePublicJiraDataset.zip --json     # 모든 카운터
```

## 스파이크 결과

**진행.** 덤프의 앞 69%(이슈 270만 개 중 200만 개)로 낸 숫자입니다. 아카이브가 인스턴스를 번갈아 담고 있어서,
나머지를 읽으면 같은 인스턴스와 아직 나오지 않은 몇 곳이 더해집니다. 병합 전에 전체 실행 결과로 바꿉니다.

| 시점 | 쓸 수 있는 릴리스 | 변별 가능(10~90% 밀림) | 10개 이상인 인스턴스 | 시작된 이슈만으로 쓸 수 있는 릴리스 |
|---|---|---|---|---|
| 출시 14일 전 | 1,888 | 1,153 | 8 | 327 |
| 출시 28일 전 | 1,795 | 1,231 | 8 | 269 |

출시 14일 전(쓸 수 있는 릴리스가 10개 이상인 인스턴스):

| 인스턴스 | 릴리스 | 레이블 있는 이슈 | 밀림 | 빠짐 | 늦음(제외) | 시작됨 | 시작됨 중 밀림 | 기간 |
|---|---|---|---|---|---|---|---|---|
| Red Hat | 948 | 55,754 | 81% | 65% | 1,977 | 11,180 | 60% | 2005–2021 |
| Apache | 326 | 22,806 | 90% | 62% | 524 | 1,784 | 70% | 2005–2021 |
| Jira | 168 | 7,180 | 62% | 43% | 515 | 1,950 | 25% | 2003–2021 |
| Spring | 149 | 6,154 | 65% | 52% | 220 | 707 | 46% | 2005–2018 |
| Qt | 116 | 6,003 | 87% | 56% | 397 | 2,575 | 80% | 2009–2021 |
| MongoDB | 107 | 6,170 | 65% | 61% | 165 | 1,534 | 43% | 2009–2021 |
| Jira Ecosystem | 50 | 1,822 | 46% | 40% | 272 | 262 | 10% | 2008–2016 |
| Sakai | 16 | 777 | 54% | 22% | 300 | 321 | 34% | 2005–2013 |

지금까지 읽은 이슈 중 7개를 빼고 모두 변경 이력이 잘리지 않았습니다.

## 벤치마크에 주는 뜻

- **예정된 이슈 대부분이 밀리고, 대개는 버전에서 빠지는 방식입니다.** 출시 2주 전에 아직 열린 이슈의 46~90%가
  그 릴리스에 들어가지 못하고, 그 대부분은 릴리스에서 빠졌습니다. 변경 이력에 남은 계획 결정이라 깔끔한
  레이블입니다. "모두 밀린다"가 정확도로는 강한 기준선이므로 PR-AUC와 릴리스별 순위를 보고하고, 반대 질문("어떤
  이슈가 들어가나")도 함께 냅니다.
- **백로그가 비율을 부풀립니다.** 버전만 붙어 있던 이슈는 시작된 이슈보다 훨씬 자주 밀립니다(Jira 62% 대 25%,
  MongoDB 65% 대 43%). 시작된 이슈 집합을 함께 내서, 손대지 않은 백로그만 알아봐도 좋아 보이는 모델을 가려냅니다.
- **변별 가능한 릴리스가 주 평가 집합입니다.** 모든 이슈가 밀렸거나 하나도 안 밀린 릴리스는 가를 것이 거의 없습니다.
- **인과가 아니라 예측입니다.** 과거 기록에는 개입이 없어서, 이 벤치마크는 T 시점에 밀림을 내다볼 수 있었는지를
  재고, 경보가 밀림을 막았을지는 재지 않습니다.
- **한계.** `releaseDate`가 계획일이 아니라 실제 출시일일 수 있고, 변경 이력에 그 변경이 남지 않아, 이를 기준으로 한
  시점은 PM이 알던 것보다 조금 나중의 지식을 씁니다. 용량 데이터가 없어 H2는 다루지 않습니다. 오픈소스 프로젝트는
  기업 PMO가 아닙니다.

## 관련 연구

- Choetkiertikul 외, [Predicting delays in software projects using networked
  classification](https://seanalytics.github.io/papers/ASE2015-preprint-choetkiertikul-dam-tran-ghose.pdf)(ASE 2015),
  [Predicting the delay of issues with due dates](https://dx.doi.org/10.1007/s10664-016-9496-7)(EMSE 2017): Jira 프로젝트의
  이슈 단위 지연 예측. 문헌 기준선과 링크 특징의 출처입니다.
- [Release readiness classification](https://old.ruhe.cpsc.ucalgary.ca/downloads/publications/conference/Release%20Readiness%20Classification.pdf):
  릴리스 준비도를 이진 분류로 다룸.

이 연구들의 숫자는 시점 재생으로 얻은 것이 아닐 수 있어, 같은 규칙으로 다시 돌린 결과만 비교합니다.
