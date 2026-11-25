#!/usr/bin/env python3
"""iOS / 프로덕트 엔지니어 / AI 빌더 채용공고 수집기.

사람인 · 잡코리아 · 자소설닷컴 · 원티드에서 공고를 모아 docs/jobs.json 으로 저장한다.
매일 GitHub Actions 에서 실행되며, 이전 결과의 first_seen 을 이어받아 "오늘 새로 뜬 공고"를 구분한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image
except ImportError:  # 로고 없이도 동작
    Image = None

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "jobs.json"
LOGO_DIR = ROOT / "docs" / "logos"
SOURCES_DIR = ROOT / "docs" / "sources"  # 서버에서 막히는 출처(원티드)를 로컬에서 긁어 둔 파일
LOCAL_MAX_AGE_DAYS = 3
MAX_NEW_LOGOS = 400
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TODAY = NOW.date()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})


def get(url: str, *, headers: dict | None = None, tries: int = 3, sleep: float = 0.6):
    last = None
    for i in range(tries):
        try:
            r = S.get(url, headers=headers, timeout=25)
            if r.status_code == 200:
                time.sleep(sleep)
                return r
            last = f"HTTP {r.status_code} {r.text[:160]!r}"
        except requests.RequestException as e:  # noqa: PERF203
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    print(f"  ! GET 실패 {url} -> {last}", file=sys.stderr)
    return None


# --------------------------------------------------------------------------- 분류 규칙
RX = {
    "ios": re.compile(r"\bios\b|swift|iphone|ipad|xcode|objective[- ]?c|애플|아이폰|아이패드|\bapple\b|cocoa|uikit", re.I),
    "product": re.compile(r"프로덕트\s*엔지니어|product\s*engineer", re.I),
    "ai_strict": re.compile(
        r"ai\s*빌더|ai\s*builder|forward[- ]?deployed|\bfde\b|\bllm\b|agentic|ai\s*agent|에이전트\s*(개발|엔지니어)|"
        r"ai\s*(engineer|엔지니어|developer|개발자|개발|product|프로덕트|서비스\s*개발|solution|솔루션|application|응용)|"
        r"(생성형|generative)\s*ai|genai|ai\s*native|ai\s*(research|리서치)", re.I),
    "ai_word": re.compile(r"\bai\b|인공지능|머신러닝|machine\s*learning|\bml\b|딥러닝|deep\s*learning", re.I),
    "dev_word": re.compile(r"개발|engineer|엔지니어|developer|builder|빌더|programmer|프로그래머|research|연구|scientist|사이언티스트", re.I),
    "mobile": re.compile(r"모바일|앱\s*개발|app\s*(developer|engineer|개발)|react\s*native|flutter|크로스\s*플랫폼|cross[- ]platform|\bapp\b", re.I),
    "public": re.compile(r"공채|공개\s*채용|신입\s*사원\s*(공개)?\s*채용|채용\s*연계형|인턴십|internship|대규모\s*채용|통합\s*채용|(상|하)반기|\d+기\b|wave|캠퍼스|global\s*internship", re.I),
    "intern": re.compile(r"인턴|intern|채용연계형", re.I),
    "junior": re.compile(r"신입|주니어|junior|entry|new\s*grad|졸업", re.I),
    "senior": re.compile(r"경력|시니어|senior|staff|lead|리드|팀장|principal|\d+\s*년", re.I),
    "any_level": re.compile(r"경력\s*무관|무관|신입\s*[·/]\s*경력|신입\s*및\s*경력", re.I),
    "it_sector": re.compile(r"개발|developer|engineer|엔지니어|프로그래머|software|소프트웨어|sw\b|\bit\b|데이터|data|ai|인공지능|머신러닝|앱|모바일|웹|백엔드|프론트|서버|클라우드|cloud|보안|security|qa|devops|infra|인프라", re.I),
}

BIGCO = [
    # 플랫폼/IT
    "삼성", "samsung", "lg", "엘지", "sk", "에스케이", "현대", "기아", "포스코", "posco", "한화", "롯데", "lotte", "cj", "씨제이",
    "신세계", "이마트", "gs", "지에스", "두산", "한진", "대한항공", "아모레", "kt", "케이티", "lgu+", "lg유플러스", "유플러스",
    "네이버", "naver", "카카오", "kakao", "쿠팡", "coupang", "토스", "toss", "비바리퍼블리카", "우아한형제들", "배달의민족",
    "라인", "line", "당근", "daangn", "두나무", "dunamu", "업비트", "크래프톤", "krafton", "엔씨", "ncsoft", "넥슨", "nexon",
    "넷마블", "netmarble", "펄어비스", "스마일게이트", "smilegate", "카카오게임즈", "데브시스터즈", "컴투스", "위메이드",
    "하이브", "hybe", "야놀자", "yanolja", "컬리", "kurly", "무신사", "musinsa", "29cm", "11번가", "지마켓", "gmarket", "옥션",
    "ssg", "카카오뱅크", "케이뱅크", "토스뱅크", "kb", "국민은행", "신한", "하나", "우리", "nh", "농협", "미래에셋", "삼성화재",
    "티맵", "tmap", "쏘카", "socar", "직방", "버킷플레이스", "오늘의집", "리디", "ridi", "왓챠", "밀리의서재", "뱅크샐러드",
    "핀다", "카카오엔터", "카카오모빌리티", "카카오페이", "카카오스타일", "카카오헬스케어", "네이버웹툰", "네이버파이낸셜",
    "네이버클라우드", "라인플러스", "soop", "아프리카", "하이퍼커넥트", "센드버드", "몰로코", "moloco", "채널코퍼레이션",
    "lg cns", "lgcns", "삼성sds", "sds", "sk c&c", "에스케이씨앤씨", "현대오토에버", "현대모비스", "현대자동차", "현대카드",
    "현대캐피탈", "삼성전자", "삼성카드", "삼성증권", "삼성생명", "교보", "한국투자", "nhn", "엔에이치엔", "kakao", "sk텔레콤",
    "skt", "sk하이닉스", "하이닉스", "sk플래닛", "11st", "ktds", "kt ds", "kt알파", "lg전자", "lg디스플레이", "lg화학",
    "lg에너지솔루션", "cj올리브", "cj enm", "cj이엔엠", "씨제이이엔엠", "롯데온", "롯데이노베이트", "신세계아이앤씨",
    "이마트24", "스타벅스", "배민", "여기어때", "마이리얼트립", "트립닷컴", "에이블리", "지그재그", "올리브영", "안랩",
    "ahnlab", "티몬", "위메프", "인터파크", "야놀자", "한국은행", "금융결제원", "한국거래소", "코스콤", "koscom",
    "삼성바이오", "셀트리온", "대웅", "유한", "한미", "넷플릭스", "netflix", "google", "구글", "apple", "애플", "microsoft",
    "마이크로소프트", "amazon", "아마존", "aws", "meta", "메타", "uber", "airbnb", "에어비앤비", "오라클", "oracle",
    "sap", "ibm", "nvidia", "엔비디아", "퀄컴", "qualcomm", "인텔", "intel", "tesla", "테슬라", "openai", "anthropic",
]


# 제목만으로는 안 잡히는 "프로덕트 엔지니어 성격" 회사. 개발 냄새가 나는 제목이면 product 로 넣는다.
WATCH_COMPANIES = ["모두닥", "아정당", "아정네트웍스", "토스", "비바리퍼블리카", "당근", "레브잇", "올웨이즈"]
WATCH_TITLE = re.compile(r"engineer|engineering|개발|developer|solver|builder|빌더|엔지니어", re.I)


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(주\)|㈜|주식회사|\(유\)|\(사\)|\(재\)|co\.?,?\s*ltd\.?|inc\.?|corp\.?", "", s)
    return re.sub(r"[\s\W_]+", "", s)


def is_bigco(company: str) -> bool:
    n = norm(company)
    if not n:
        return False
    for b in BIGCO:
        if norm(b) and norm(b) in n:
            return True
    return False


RX.update({
    "android_only": re.compile(r"android|안드로이드|kotlin", re.I),
    "strong_dev": re.compile(r"개발자|엔지니어|engineer\b|developer|프로그래머|programmer|개발\s*\(|개발$|개발자|개발\)|software|소프트웨어", re.I),
    "hard_drop": re.compile(r"교육생|부트캠프|bootcamp|양성\s*과정|훈련생|국비|수강생|교육과정|취업\s*연계\s*교육|아카데미|SeSAC|사관학교|프로젝트\s*안내|인력\s*풀|상시\s*인재\s*풀", re.I),
    "non_dev": re.compile(r"기획자|기획\b|서비스\s*기획|마케터|마케팅|디자이너|designer|영업|세일즈|sales|회계|인사\b|총무|법무|\bPO\b|프로덕트\s*오너|product\s*owner|product\s*manager|프로덕트\s*매니저|\bPM\b|project\s*manager|매니저|강사|상담|\bCS\b|고객\s*(지원|응대)|감사|검수|테크니컬\s*라이터|리크루터|채용\s*담당|운영\s*담당|관리자|본부장|스태프|어시스턴트|비서|애널리스트|analyst|컨설턴트|consultant|리서처\b|한약|생물학|임상|간호", re.I),
    "hw": re.compile(r"반도체|emmc|메모리\s*(제품|반도체)|\bmcp\b|공정|장비\s*(제어|개발|엔지니어)|plastics|소재|화학|기계\s*(설계|엔지니어)|전장|회로|pcb|fpga|rtl|아날로그|광학|배터리|용접|금형|사출|품질\s*(검사|관리|보증)|생산\s*(관리|기술)", re.I),
    "it_strict": re.compile(r"소프트웨어|software|\bsw\b|앱\s*개발|모바일|\bios\b|android|웹\s*개발|백엔드|backend|프론트|frontend|서버\s*개발|클라우드|cloud|데이터\s*(엔지니어|분석|사이언)|data\s*(engineer|scientist)|\bai\b|인공지능|머신러닝|딥러닝|\bml\b|llm|보안|security|devops|인프라\s*엔지니어|개발자|developer|프로그래머|programmer|전산(?!회계)|정보기술|정보시스템|\bit\s*(개발|운영|기획|엔지니어)|시스템\s*(개발|엔지니어|운영)|sre\b|플랫폼\s*개발|solution\s*engineer|솔루션\s*(개발|엔지니어)", re.I),
})


def classify(title: str, sector: str = "") -> list[str]:
    """제목 기준으로 분류한다. sector(직무 태그)는 제목이 일반적인 '개발자/엔지니어'일 때만 보조로 쓴다."""
    t = title or ""
    if RX["hard_drop"].search(t):
        return []
    strong = bool(RX["strong_dev"].search(t))
    if RX["non_dev"].search(t) and not strong:
        return []
    cats = []
    ios = bool(RX["ios"].search(t))
    android_only = bool(RX["android_only"].search(t)) and not ios
    if not ios and strong and sector and RX["ios"].search(sector) and not android_only \
            and re.search(r"앱|\bapp\b|mobile|모바일|클라이언트|client|\bmts\b|네이티브|native", t, re.I) \
            and not re.search(r"frontend|프론트|backend|백엔드|server|서버|web|웹|java\b|php|python|node|\.net|c\+\+|unity|클라우드|cloud|data|데이터|devops|인프라|qa\b|보안", t, re.I):
        ios = True
    if ios:
        cats.append("ios")
    if (RX["product"].search(t) or re.search(r"problem\s*solver.*(engineer|engineering)|engineering\s*based", t, re.I)) and not RX["hw"].search(t):
        cats.append("product")
    if (RX["ai_strict"].search(t) or (RX["ai_word"].search(t) and RX["dev_word"].search(t))) and not RX["hw"].search(t):
        cats.append("ai")
    if not ios and not android_only and RX["mobile"].search(t) and strong:
        cats.append("mobile")
    return cats


def is_it_role(title: str, sector: str = "") -> bool:
    """공채 항목 중 개발/IT 직군인지. 하드웨어·화학 등은 제외."""
    text = f"{title} {sector}"
    if RX["hard_drop"].search(title) or RX["hw"].search(text):
        return False
    if RX["non_dev"].search(title) and not RX["strong_dev"].search(title):
        return False
    return bool(RX["it_strict"].search(text))


def level_of(text: str) -> str:
    if RX["intern"].search(text):
        return "intern"
    if RX["any_level"].search(text):
        return "any"
    j, s = bool(RX["junior"].search(text)), bool(RX["senior"].search(text))
    if j and s:
        return "any"
    if j:
        return "junior"
    if s:
        return "senior"
    return "unknown"


SIDO = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def region_key(region: str) -> str | None:
    r = (region or "").strip()
    if not r:
        return None
    for sd in SIDO:
        if r.startswith(sd) or f" {sd}" in r[:12]:
            return sd
    if re.search(r"해외|일본|미국|싱가포르|베트남|도쿄|remote|원격|재택", r, re.I):
        return "해외/원격"
    return "기타"


def parse_mmdd(s: str) -> str | None:
    """'~ 12/07(월)' / '~11.30(월)' 같은 문자열을 ISO 날짜로. 연도는 오늘 기준으로 추정."""
    s = s or ""
    if re.search(r"오늘\s*마감", s):
        return TODAY.isoformat()
    if re.search(r"내일\s*마감", s):
        return (TODAY + dt.timedelta(days=1)).isoformat()
    dm = re.search(r"D-(\d+)", s)
    if dm:
        return (TODAY + dt.timedelta(days=int(dm.group(1)))).isoformat()
    m = re.search(r"(\d{1,2})[./](\d{1,2})", s)
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    y = TODAY.year
    try:
        cand = dt.date(y, mo, d)
    except ValueError:
        return None
    if (cand - TODAY).days < -60:  # 작년 아닌 내년
        cand = dt.date(y + 1, mo, d)
    return cand.isoformat()


def make(source, sid, title, company, url, **kw):
    cats = kw.pop("cats", None)
    if cats is None:
        cats = classify(title, kw.get("sector", ""))
        if not cats and any(norm(w) in norm(company) for w in WATCH_COMPANIES) and WATCH_TITLE.search(title) \
                and not RX["non_dev"].search(title):
            cats = ["product"]
    job = {
        "id": f"{source}:{sid}",
        "source": source,
        "title": title.strip(),
        "company": company.strip(),
        "url": url,
        "cats": cats,
        "level": kw.get("level") or level_of(" ".join(filter(None, [title, kw.get("cond", "")]))),
        "region": (kw.get("region") or "").strip() or None,
        "region_key": region_key(kw.get("region") or ""),
        "deadline": kw.get("deadline"),  # ISO date or None(상시/미정)
        "deadline_text": kw.get("deadline_text"),
        "posted": kw.get("posted"),  # ISO date or None
        "public": bool(kw.get("public")) or bool(RX["public"].search(title)),
        "bigco": bool(kw.get("bigco")) or is_bigco(company),
        "sector": kw.get("sector") or None,
        "employment_type": kw.get("employment_type"),
        "salary": kw.get("salary"),
        "group": kw.get("group"),
        "logo_url": kw.get("logo_url"),
    }
    return job


# --------------------------------------------------------------------------- 원티드
WANTED_H = {"Accept": "application/json", "Referer": "https://www.wanted.co.kr/",
            "wanted-user-country": "KR", "wanted-user-language": "ko"}


def wanted_job(j, cats=None):
    addr = j.get("address") or {}
    region = " ".join(filter(None, [addr.get("location"), addr.get("district")]))
    due = j.get("due_time")
    return make(
        "wanted", j["id"], j.get("position", ""), (j.get("company") or {}).get("name", ""),
        f"https://www.wanted.co.kr/wd/{j['id']}",
        region=region, deadline=due[:10] if due else None,
        deadline_text=None if due else "상시",
        cond=f"경력 {j.get('annual_from')}~{j.get('annual_to')}년",
        logo_url=((j.get("logo_img") or {}).get("thumb")),
        level=("junior" if j.get("annual_from") == 0 and (j.get("annual_to") or 0) <= 1
               else "any" if j.get("annual_from") == 0 else "senior") if j.get("annual_from") is not None else None,
        cats=cats,
    )


def scrape_wanted():
    out = {}
    # 1) iOS 개발자 직군 태그(677) 전체
    for offset in range(0, 400, 100):
        r = get(f"https://www.wanted.co.kr/api/v4/jobs?country=kr&tag_type_ids=677&job_sort=job.latest_order"
                f"&locations=all&years=-1&limit=100&offset={offset}", headers=WANTED_H)
        if not r:
            break
        data = r.json().get("data", [])
        for j in data:
            job = wanted_job(j)
            title = job["title"]
            if not job["cats"]:
                if RX["hard_drop"].search(title) or RX["android_only"].search(title) or \
                        re.search(r"frontend|프론트|backend|백엔드|server|서버|\bweb\b|웹|java\b|php|python|node|\.net|c\+\+|unity|unreal|클라우드|cloud|data|데이터|devops|인프라|qa\b|보안|manager|매니저|기획|designer|디자이너|pm\b|embedded|임베디드|firmware|os engineer|camera|flutter|react native|풀스택|full.?stack|solution|architect|test|automation|ad-tech|growth|research|리서치", title, re.I) or \
                        not re.search(r"engineer|developer|개발자|엔지니어|\bapp\b|앱|mobile|모바일|sdk|client|클라이언트", title, re.I):
                    continue
                job["cats"] = ["ios"]  # 원티드 iOS 직군 태그 + 일반적인 제목(예: Senior Engineer)
            elif "ios" not in job["cats"] and "mobile" not in job["cats"]:
                continue  # iOS 태그가 달렸지만 제목은 다른 직군(Android 등)
            out[job["id"]] = job
        if len(data) < 100:
            break
    # 2) 키워드 검색. 원티드 검색은 공고 본문까지 매칭하므로(예: "AI 빌더" ≈ "AI") 깊게 긁은 뒤 제목으로 거른다.
    for q, max_off in [("AI", 1500), ("Product Engineer", 800), ("프로덕트 엔지니어", 800), ("Forward Deployed", 300),
                       ("LLM", 600), ("Agent", 600), ("iOS", 600), ("Swift", 300)] + [(w, 100) for w in WATCH_COMPANIES]:
        seen_empty = 0
        for offset in range(0, max_off, 100):
            r = get(f"https://www.wanted.co.kr/api/v4/search?country=kr&query={quote(q)}&job_sort=job.latest_order"
                    f"&years=-1&locations=all&limit=100&offset={offset}", headers=WANTED_H, sleep=0.3)
            if not r:
                break
            jobs = (r.json().get("data") or {}).get("jobs") or []
            if not jobs:
                break
            new = 0
            for j in jobs:
                if f"wanted:{j['id']}" in out:
                    continue
                job = wanted_job(j)
                if job["cats"]:
                    out[job["id"]] = job
                    new += 1
            seen_empty = seen_empty + 1 if new == 0 else 0
            if len(jobs) < 100 or seen_empty >= 4:
                break
    return list(out.values())


# --------------------------------------------------------------------------- 사람인
def saramin_search(q, pages=2, extra=""):
    jobs = []
    for p in range(1, pages + 1):
        r = get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&searchword={quote(q)}"
                f"&recruitSort=reg_dt&recruitPageCount=40&recruitPage={p}{extra}")
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select(".item_recruit")
        for it in items:
            a = it.select_one(".job_tit a")
            if not a:
                continue
            rec = it.get("value") or re.search(r"rec_idx=(\d+)", a.get("href", "")).group(1)
            corp = it.select_one(".corp_name a") or it.select_one(".corp_name")
            conds = [s.get_text(" ", strip=True) for s in it.select(".job_condition span")]
            sector = ", ".join(x.get_text(strip=True) for x in it.select(".job_sector a"))
            day = it.select_one(".job_day")
            posted = None
            if day:
                m = re.search(r"(\d{2})/(\d{2})/(\d{2})", day.get_text())
                if m:
                    posted = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
            dtext = (it.select_one(".job_date .date") or it.new_tag("x")).get_text(strip=True)
            jobs.append(make(
                "saramin", rec, a.get("title") or a.get_text(strip=True), corp.get_text(strip=True) if corp else "",
                f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec}",
                region=conds[0] if conds else "", cond=" ".join(conds[1:]), sector=sector,
                deadline=parse_mmdd(dtext), deadline_text=None if parse_mmdd(dtext) else (dtext or None),
                posted=posted, employment_type=next((c for c in conds if re.search(r"정규직|계약직|인턴|프리랜서|파견", c)), None),
                bigco=("scale001" in extra) or None,
            ))
        if len(items) < 40:
            break
    return jobs


def scrape_saramin():
    out = {}
    for q, pages, extra in [
        ("iOS", 3, ""), ("Swift", 1, ""), ("SwiftUI", 1, ""), ("iOS 개발자", 1, ""),
        ("프로덕트 엔지니어", 1, ""), ("Product Engineer", 1, ""),
        ("AI 빌더", 1, ""), ("AI Engineer", 2, ""), ("AI 엔지니어", 1, ""), ("Forward Deployed Engineer", 1, ""), ("LLM", 1, ""),
        ("iOS", 1, "&company_type=scale001"), ("AI", 1, "&company_type=scale001"),
    ]:
        for job in saramin_search(q, pages, extra):
            if not job["cats"]:
                continue
            if job["id"] in out:
                out[job["id"]]["bigco"] = out[job["id"]]["bigco"] or job["bigco"]
            else:
                out[job["id"]] = job
    # 공채속보 (대기업 공채) 중 IT 직군만
    for p in range(1, 6):
        r = get(f"https://www.saramin.co.kr/zf_user/jobs/public/list?page={p}")
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select(".list_item")
        for it in items:
            a = it.select_one(".job_tit a")
            if not a:
                continue
            m = re.search(r"rec_idx=(\d+)", a.get("href", ""))
            if not m:
                continue
            rec = m.group(1)
            title = a.get("title") or a.get_text(strip=True)
            sector = ", ".join(s.get_text(strip=True) for s in it.select(".job_sector span"))
            cats = classify(title, sector)
            if not cats and not is_it_role(title, sector):
                continue
            if not cats:
                cats = ["dev"]
            corp = it.select_one(".company_nm .str_tit")
            grp = it.select_one(".main_corp")
            big = it.select_one(".info_stock")
            career = (it.select_one(".career") or it.new_tag("x")).get_text(strip=True)
            dtext = (it.select_one(".support_detail .date") or it.new_tag("x")).get_text(strip=True)
            job = make(
                "saramin", rec, title, corp.get_text(strip=True) if corp else "",
                f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec}",
                region=(it.select_one(".work_place") or it.new_tag("x")).get_text(strip=True),
                cond=career, sector=sector, cats=cats, public=True,
                deadline=parse_mmdd(dtext), deadline_text=None if parse_mmdd(dtext) else (dtext or None),
                bigco=bool(big and "대기업" in big.get_text()), group=grp.get_text(strip=True) if grp else None,
                employment_type=next((c for c in ("정규직", "계약직", "인턴") if c in career), None),
                salary=(it.select_one(".salary") or it.new_tag("x")).get_text(strip=True) or None,
            )
            out.setdefault(job["id"], job)
        if len(items) < 20:
            break
    return list(out.values())


# --------------------------------------------------------------------------- 잡코리아
def jobkorea_search(q, pages=2):
    jobs = []
    for p in range(1, pages + 1):
        r = get(f"https://www.jobkorea.co.kr/Search/?stext={quote(q)}&ord=RegDtDesc&tabType=recruit&Page_No={p}")
        if not r:
            break
        soup = BeautifulSoup(r.text, "lxml")
        cards = soup.select('[data-sentry-component="CardJob"]')
        for c in cards:
            t = c.select_one('[data-sentry-component="Title"]')
            if not t:
                continue
            href = t.get("href", "")
            m = re.search(r"GI_Read/(\d+)", href)
            if not m:
                continue
            gno = m.group(1)
            title = t.get_text(" ", strip=True)
            comp_a = t.find_parent().find_next_sibling()  # 회사명 링크
            company = next(iter(comp_a.stripped_strings), "") if comp_a else ""
            chips = [x.get_text(" ", strip=True) for x in c.select('[data-sentry-component="GrayChip"]')]
            strings = list(c.stripped_strings)
            region = chips[0] if chips else ""
            sector = chips[1] if len(chips) > 1 else ""
            cond = " ".join(s for s in strings if re.search(r"경력|신입|무관|인턴|정규직|계약직|프리랜서|재택", s))
            salary = next((s for s in strings if "연봉" in s or "월급" in s), None)
            badges = [x.get_text(" ", strip=True) for x in c.select('[data-sentry-component="BadgeItem"]')]
            img = c.select_one('img[alt$="로고"]')
            logo = img.get("src") if img else None
            if logo and re.search(r"noimg|no_img|default|blank|_logo_none", logo, re.I):
                logo = None
            jobs.append(make(
                "jobkorea", gno, title, company, f"https://www.jobkorea.co.kr/Recruit/GI_Read/{gno}",
                region=region, cond=cond, sector=sector, salary=salary,
                posted=TODAY.isoformat() if any("오늘" in b for b in badges) else None,
                logo_url=logo,
                employment_type=next((x for x in ("정규직", "계약직", "인턴", "프리랜서") if x in cond), None),
                deadline_text=None,
            ))
        if len(cards) < 20:
            break
    return jobs


def scrape_jobkorea():
    out = {}
    for q, pages in [("iOS", 3), ("Swift", 1), ("SwiftUI", 1), ("iOS 개발자", 1),
                     ("프로덕트 엔지니어", 1), ("Product Engineer", 1),
                     ("AI 빌더", 1), ("AI Engineer", 2), ("AI 엔지니어", 1), ("Forward Deployed", 1), ("LLM", 1)]:
        for job in jobkorea_search(q, pages):
            if job["cats"]:
                out.setdefault(job["id"], job)
    return list(out.values())


# --------------------------------------------------------------------------- 자소설닷컴
IT_DUTY = {161, 162, 163, 164, 165, 167, 168}  # 앱개발, 웹개발, 데이터, 시스템, 응용, 빅데이터AI, 게임개발


def scrape_jasoseol():
    out = {}
    hdr = {"Accept": "application/json"}
    for p in range(1, 8):
        r = get(f"https://jasoseol.com/api/v1/employment_companies?page={p}&per_page=100"
                f"&after_end_time={TODAY.isoformat()}&sort=-created_at", headers=hdr)
        if not r:
            break
        data = r.json()
        if not isinstance(data, list):
            break
        for c in data:
            end = c.get("end_time")
            rolling = c.get("recruit_type") == 1
            for e in c.get("employments", []):
                field = e.get("field") or ""
                ctitle = c.get("title", "")
                duty = set(e.get("duty_group_ids") or [])
                if RX["hard_drop"].search(ctitle) or RX["hard_drop"].search(field):
                    continue
                cats = classify(field) or classify(ctitle)
                it = bool(IT_DUTY & duty) and len(duty) <= 10 and is_it_role(f"{ctitle} {field}")
                if not cats and not it:
                    continue
                if not cats:
                    cats = ["dev"]
                eend = e.get("end_time") or end
                title = f"{c.get('title','')} · {field}" if field and field not in c.get("title", "") else c.get("title", "")
                job = make(
                    "jasoseol", f"{c['id']}-{e['id']}", title, c.get("name", ""),
                    f"https://jasoseol.com/recruit/{c['id']}",
                    cats=cats, public=not rolling, cond=c.get("title", ""),
                    deadline=eend[:10] if (eend and not rolling) else None,
                    deadline_text="수시" if rolling else None,
                    posted=(c.get("opened_at") or c.get("created_at") or "")[:10] or None,
                    extra=field, logo_url=c.get("image_url"),
                )
                out[job["id"]] = job
        if len(data) < 100:
            break
    return list(out.values())


# --------------------------------------------------------------------------- 로고
def logo_file(company: str) -> str:
    return f"logos/{hashlib.md5(norm(company).encode()).hexdigest()[:12]}.png"


def fetch_logo(company: str, url: str) -> str | None:
    rel = logo_file(company)
    path = ROOT / "docs" / rel
    if path.exists():
        return rel
    if not url or Image is None:
        return None
    if url.startswith("//"):
        url = "https:" + url
    try:
        r = S.get(url, timeout=10)
        if r.status_code != 200 or len(r.content) < 200:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
        im.thumbnail((96, 96))
        canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        canvas.paste(im, ((96 - im.width) // 2, (96 - im.height) // 2))
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        canvas.save(path, "PNG", optimize=True)
        return rel
    except Exception:  # noqa: BLE001
        return None


def attach_logos(jobs: list[dict]) -> int:
    """회사명 기준으로 로고를 공유한다(사람인처럼 로고가 없는 출처도 다른 사이트 로고를 쓴다)."""
    url_by_co: dict[str, str] = {}
    for j in jobs:
        if j.get("logo_url"):
            url_by_co.setdefault(norm(j["company"]), j["logo_url"])
    downloaded = 0
    cache: dict[str, str | None] = {}
    for j in jobs:
        key = norm(j["company"])
        if key not in cache:
            rel = logo_file(j["company"])
            if (ROOT / "docs" / rel).exists():
                cache[key] = rel
            elif url_by_co.get(key) and downloaded < MAX_NEW_LOGOS:
                cache[key] = fetch_logo(j["company"], url_by_co[key])
                downloaded += 1
            else:
                cache[key] = None
        j["logo"] = cache[key]
        j.pop("logo_url", None)
    return downloaded


# --------------------------------------------------------------------------- 메인
SOURCES = {
    "wanted": ("원티드", scrape_wanted),
    "saramin": ("사람인", scrape_saramin),
    "jobkorea": ("잡코리아", scrape_jobkorea),
    "jasoseol": ("자소설닷컴", scrape_jasoseol),
}


def load_local_source(key: str):
    """로컬(한국 IP)에서 미리 수집해 둔 docs/sources/<key>.json 을 읽는다. 오래됐으면 None."""
    path = SOURCES_DIR / f"{key}.json"
    if not path.exists():
        return None, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        fetched = dt.datetime.fromisoformat(doc["fetched_at"])
        if (NOW - fetched).days > LOCAL_MAX_AGE_DAYS:
            return None, doc["fetched_at"]
        return doc["jobs"], doc["fetched_at"]
    except Exception:  # noqa: BLE001
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="쉼표로 구분한 출처만 수집해 docs/sources/<출처>.json 에 저장 (jobs.json 은 건드리지 않음)")
    args = ap.parse_args()
    if args.only:
        for key in args.only.split(","):
            label, fn = SOURCES[key]
            found = fn()
            if not found:
                print(f"{label}: 0건, 파일 유지", file=sys.stderr)
                continue
            attach_logos(found)
            SOURCES_DIR.mkdir(parents=True, exist_ok=True)
            (SOURCES_DIR / f"{key}.json").write_text(
                json.dumps({"fetched_at": NOW.isoformat(timespec="minutes"), "jobs": found}, ensure_ascii=False), encoding="utf-8")
            print(f"{label}: {len(found)}건 → docs/sources/{key}.json")
        return

    prev = {}
    prev_meta = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            prev = {j["id"]: j for j in old.get("jobs", [])}
            prev_meta = old.get("sources", {})
        except Exception:  # noqa: BLE001
            pass

    jobs: dict[str, dict] = {}
    meta = {}
    for key, (label, fn) in SOURCES.items():
        t0 = time.time()
        try:
            found = fn()
            err = None
        except Exception:  # noqa: BLE001
            found, err = [], traceback.format_exc(limit=3)
            print(f"  ! {label} 실패\n{err}", file=sys.stderr)
        local_note = None
        if not found:
            local_jobs, fetched_at = load_local_source(key)
            if local_jobs:
                found, err = local_jobs, None
                local_note = f"로컬 수집 {fetched_at}"
        if not found:
            # 이번 런에서 실패/0건이면 직전 결과를 유지(stale)
            kept = [dict(j, stale=True) for j in prev.values() if j["source"] == key]
            for j in kept:
                jobs[j["id"]] = j
            meta[key] = {"label": label, "count": len(kept), "ok": False, "error": err or "0건",
                         "last_ok": prev_meta.get(key, {}).get("last_ok")}
        else:
            for j in found:
                jobs[j["id"]] = j
            meta[key] = {"label": label, "count": len(found), "ok": True, "error": None, "note": local_note,
                         "last_ok": local_note.split(" ", 2)[-1] if local_note else NOW.isoformat(timespec="minutes")}
        print(f"{label}: {meta[key]['count']}건 ({time.time()-t0:.0f}s)")

    # 마감 지난 공고 제거, first_seen 이어받기
    final = []
    for j in jobs.values():
        if j.get("deadline") and j["deadline"] < TODAY.isoformat():
            continue
        p = prev.get(j["id"])
        j["first_seen"] = p.get("first_seen") if p and p.get("first_seen") else TODAY.isoformat()
        if not j.get("posted"):
            j["posted"] = p.get("posted") if p and p.get("posted") else j["first_seen"]
        j["last_seen"] = TODAY.isoformat()
        j.setdefault("stale", False)
        final.append(j)

    # 같은 회사+같은 제목은 하나로 묶고 다른 출처 링크를 보존
    merged: dict[str, dict] = {}
    for j in sorted(final, key=lambda x: (x["source"] != "saramin", x["source"] != "wanted", x["id"])):
        k = f"{norm(j['company'])}|{norm(j['title'])}"
        if k in merged:
            m = merged[k]
            m.setdefault("also", []).append({"source": j["source"], "url": j["url"]})
            m["bigco"] = m["bigco"] or j["bigco"]
            m["public"] = m["public"] or j["public"]
            m["cats"] = sorted(set(m["cats"]) | set(j["cats"]), key=["ios", "product", "ai", "mobile", "dev"].index)
            if j["first_seen"] < m["first_seen"]:
                m["first_seen"] = j["first_seen"]
        else:
            merged[k] = j
    final = sorted(merged.values(), key=lambda x: (x["first_seen"], x.get("posted") or ""), reverse=True)
    n_logo = attach_logos(final)
    print(f"로고: 새로 {n_logo}개 내려받음, 로고 있는 공고 {sum(1 for j in final if j.get('logo'))}/{len(final)}")

    cats = {c: sum(1 for j in final if c in j["cats"]) for c in ["ios", "product", "ai", "mobile", "dev"]}
    doc = {
        "updated_at": NOW.isoformat(timespec="minutes"),
        "today": TODAY.isoformat(),
        "sources": meta,
        "stats": {"total": len(final), "new_today": sum(1 for j in final if j["first_seen"] == TODAY.isoformat()),
                  "bigco": sum(1 for j in final if j["bigco"]), "public": sum(1 for j in final if j["public"]), "cats": cats},
        "jobs": final,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"총 {len(final)}건 저장 → {OUT}  (오늘 신규 {doc['stats']['new_today']}, 카테고리 {cats})")


if __name__ == "__main__":
    main()
