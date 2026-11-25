# 채용 레이더 (jobs)

사람인 · 잡코리아 · 자소설닷컴 · 원티드의 **iOS / 프로덕트 엔지니어 / AI 빌더 / 개발 공채** 공고를 매일 아침 9시(KST)에 모아서 한 페이지로 보여준다.

- `scraper/scrape.py` — 네 사이트를 돌며 공고를 모으고 분류해 `docs/jobs.json`에 저장
- `docs/index.html` — 필터/검색이 되는 정적 페이지 (GitHub Pages로 서빙)
- `.github/workflows/update.yml` — 매일 수집 → `jobs.json` 커밋

## 분류

| 구분 | 기준 |
| --- | --- |
| iOS | 제목에 iOS / Swift / 애플 등, 또는 원티드 iOS 직군 태그 |
| 프로덕트 엔지니어 | Product Engineer / 프로덕트 엔지니어 |
| AI 빌더 | AI 빌더, Forward Deployed Engineer(FDE), AI Engineer, LLM, AI Agent 등 |
| 모바일(크로스플랫폼) | React Native / Flutter / 앱 개발자 (iOS 명시 없음) |
| 개발 공채 | 자소설닷컴·사람인 공채속보 중 IT 직군 (iOS 아님) |

그 외 `대기업`(그룹사·주요 IT기업 목록 + 사람인 대기업 배지), `공채`(공개채용·인턴십·채용연계형 등), 신입/경력/인턴, 지역, 마감일을 같이 저장한다. 같은 회사·같은 제목은 하나로 합치고 다른 사이트 링크는 `also`에 보관한다.

## 로컬 실행

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scraper/scrape.py          # docs/jobs.json 생성
python -m http.server -d docs 8000  # http://localhost:8000
```

## 배포 (처음 한 번)

```bash
gh repo create jobs --public --source=. --push
gh api -X POST repos/{owner}/jobs/pages -f 'source[branch]=main' -f 'source[path]=/docs'
gh workflow run "채용공고 수집"
```

이후엔 매일 자동으로 돌고, 페이지는 `https://<계정>.github.io/jobs/` 에서 열린다.

## 메모

- 사람인·잡코리아는 HTML을 긁고, 원티드·자소설닷컴은 내부 JSON API를 쓴다. 사이트 구조가 바뀌면 해당 소스만 0건이 되고, 이전 결과를 `stale` 표시로 유지한다. 페이지 상단에 소스별 상태가 뜬다.
- 잡코리아 카드에는 마감일이 없어서 비어 있다. 원티드는 대부분 상시채용이다.

## 로고

원티드·잡코리아·자소설닷컴에서 회사 로고를 받아 `docs/logos/<회사명 해시>.png`(96px)로 저장하고, 같은 회사명이면 사람인 공고에도 재사용한다. 로고가 없으면 회사명 첫 글자로 대체한다.

## 관심 기업

제목만으로는 분류가 안 되는 회사(예: 모두닥 "Problem Solver (Engineering Based)")는 `scraper/scrape.py`의 `WATCH_COMPANIES`에 넣으면 원티드에서 회사명으로 추가 검색하고, 개발 성격의 제목이면 프로덕트 엔지니어로 넣는다.

## 원티드는 맥에서 수집 (하이브리드)

원티드(CloudFront)는 GitHub Actions 러너 IP(미국)를 403으로 막는다. 그래서 원티드만 한국 IP인 맥에서 긁는다.

- `scripts/wanted_local.sh` — `scrape.py --only wanted` 로 `docs/sources/wanted.json` + 로고를 만들어 푸시. launchd(`~/Library/LaunchAgents/com.jeonguk.jobs-wanted.plist`)가 매일 08:30 실행, 로그는 `~/Library/Logs/jobs-wanted.log`.
- 그 푸시가 워크플로를 바로 트리거하고, 워크플로는 원티드가 막히면 `docs/sources/wanted.json`(3일 이내)을 대신 쓴다. 맥이 꺼져 있던 날은 원티드만 직전 데이터("갱신 대기")로 남는다.
- 끄려면: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.jeonguk.jobs-wanted.plist`
