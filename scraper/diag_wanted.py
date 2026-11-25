"""GitHub 러너에서 원티드가 왜 403인지 변형별로 찍어본다."""
import requests
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
API = "https://www.wanted.co.kr/api/v4/jobs?country=kr&tag_type_ids=677&job_sort=job.latest_order&locations=all&years=-1&limit=5&offset=0"
tests = {
    "a_current": (API, {**BASE, "Accept": "application/json", "Referer": "https://www.wanted.co.kr/", "wanted-user-country": "KR", "wanted-user-language": "ko"}),
    "b_full_browser": (API, {**BASE, "Accept": "application/json, text/plain, */*", "Accept-Encoding": "gzip, deflate, br", "Referer": "https://www.wanted.co.kr/wdlist/518/677",
                              "Origin": "https://www.wanted.co.kr", "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
                              "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"', "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"macOS"',
                              "wanted-user-country": "KR", "wanted-user-language": "ko"}),
    "c_html_wdlist": ("https://www.wanted.co.kr/wdlist/518/677", {**BASE, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}),
    "d_chaos": ("https://www.wanted.co.kr/api/chaos/navigation/v1/results?job_group_id=518&job_ids=677&country=kr&job_sort=job.latest_order&years=-1&locations=all&limit=5&offset=0",
                {**BASE, "Accept": "application/json", "Referer": "https://www.wanted.co.kr/"}),
    "e_mobile_ua": (API, {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "Accept": "application/json", "Referer": "https://www.wanted.co.kr/"}),
    "f_root": ("https://www.wanted.co.kr/", {**BASE, "Accept": "text/html"}),
    "g_global": ("https://www.wanted.co.kr/api/v4/jobs?country=kr&tag_type_ids=677&limit=5&offset=0", {**BASE, "Accept": "application/json", "Referer": "https://www.wantedly.com/"}),
}
ip = requests.get("https://api.ipify.org", timeout=10).text
print("runner ip", ip)
for k, (u, h) in tests.items():
    try:
        r = requests.get(u, headers=h, timeout=20)
        print(f"{k}: {r.status_code} len={len(r.content)} via={r.headers.get('via','')[:40]} x-cache={r.headers.get('x-cache','')} body={r.text[:90]!r}")
    except Exception as e:
        print(f"{k}: ERR {e!r}")
