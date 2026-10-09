#!/usr/bin/env python3
"""Свежие вакансии: администрирование сайтов, WordPress, no-code, автоматизация.

Источники: DOU (RSS), Djinni (RSS), Himalayas (JSON API). Только стандартная библиотека.
Печатает компактный список вакансий, опубликованных за последние N часов.

  python3 -I fetch_jobs.py            # окно выбирается само по времени в Киеве
  python3 -I fetch_jobs.py --hours 72 # явное окно
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
HEADERS = {"User-Agent": "Mozilla/5.0 (job-digest)"}

DOU_SEARCHES = ["", "wordpress", "адміністратор сайту", "контент-менеджер", "webflow",
                "tilda", "shopify", "n8n", "автоматизац", "no-code", "webmaster"]
DJINNI_FEEDS = ["", "?primary_keyword=WordPress"]
HIMALAYAS_SEARCHES = ["wordpress", "webmaster", "website manager", "no-code", "n8n"]

# Совпадение ищем только в названии вакансии (и категории Djinni): описания дают много шума.
INCLUDE = re.compile(
    r"wordpress|woocommerce|сайт|website|web ?site|webmaster|веб-?майстер|вебмастер|\bcms\b|"
    r"tilda|webflow|shopify|wix|elementor|контент|content manager|hosting|хостинг|domain|домен|"
    r"n8n|make\.com|zapier|no-?code|low-?code|automation|автоматиз|web developer|веб-розроб|"
    r"веб-разраб|wp\b",
    re.I)
EXCLUDE = re.compile(
    r"\bjava\b|\bios\b|android|\bqa\b|tester|test engineer|devops|data (?:engineer|scientist)|"
    r"\.net\b|c\+\+|golang|unity|game|\bsales\b|продаж|recruit|accountant|бухгалт|"
    r"instructor|викладач|mentor|ментор|\btest|тестуван|\baqa\b|військов|python developer|"
    r"software engineer|full-stack engineer",
    re.I)


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def snippet(text, n=150):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


def relevant(title, extra=""):
    return bool(INCLUDE.search(f"{title} {extra}")) and not EXCLUDE.search(title)


def from_rss(source, url, since, with_snippet):
    root = ET.fromstring(fetch(url))
    for item in root.iter("item"):
        title = html.unescape(item.findtext("title") or "").strip()
        cats = " ".join(c.text or "" for c in item.findall("category"))
        published = parsedate_to_datetime(item.findtext("pubDate"))
        if published < since or not relevant(title, cats):
            continue
        link = (item.findtext("link") or "").split("?utm_")[0]
        info = snippet(item.findtext("description")) if with_snippet else ""
        yield link, published, source, title, info


def from_himalayas(query, since):
    url = "https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode({"q": query, "limit": 20})
    for job in json.loads(fetch(url)).get("jobs", []):
        published = datetime.fromtimestamp(job.get("pubDate") or 0, timezone.utc)
        allowed = job.get("locationRestrictions") or []
        if published < since or not relevant(job.get("title", "")):
            continue
        if allowed and "Ukraine" not in allowed:
            continue
        salary = ""
        if job.get("minSalary"):
            salary = f"{job['minSalary']}–{job.get('maxSalary') or ''} {job.get('currency') or ''}/{job.get('salaryPeriod') or ''}, "
        where = "Ukraine OK" if allowed else "worldwide"
        info = f"{job.get('companyName')}, {salary}{where}, {job.get('employmentType') or ''}. {snippet(job.get('excerpt'), 120)}"
        link = job.get("applicationLink") or job.get("guid")
        yield link, published, "Himalayas", job.get("title", ""), info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, help="окно поиска в часах (по умолчанию: 15 утром, иначе 6)")
    args = parser.parse_args()
    now = datetime.now(KYIV)
    hours = args.hours or (15 if now.hour < 11 else 6)
    since = now - timedelta(hours=hours)

    sources = [("DOU", f"https://jobs.dou.ua/vacancies/feeds/?{urllib.parse.urlencode({'search': q})}" if q
                else "https://jobs.dou.ua/vacancies/feeds/", False) for q in DOU_SEARCHES]
    sources += [("Djinni", f"https://djinni.co/jobs/rss/{q}", True) for q in DJINNI_FEEDS]

    jobs, errors = {}, []
    for source, url, with_snippet in sources:
        try:
            for job in from_rss(source, url, since, with_snippet):
                jobs.setdefault(job[0], job)
        except Exception as exc:  # один упавший источник не должен ломать остальные
            errors.append(f"{source} {url}: {exc}")
    for query in HIMALAYAS_SEARCHES:
        try:
            for job in from_himalayas(query, since):
                jobs.setdefault(job[0], job)
        except Exception as exc:
            errors.append(f"Himalayas {query}: {exc}")

    print(f"# окно: последние {hours:g} ч (с {since:%d.%m %H:%M} по Киеву), найдено: {len(jobs)}")
    for link, published, source, title, info in sorted(jobs.values(), key=lambda j: j[1], reverse=True):
        line = f"- [{source}] {title} | {published.astimezone(KYIV):%d.%m %H:%M} | {link}"
        print(line + (f"\n    {info}" if info else ""))
    for err in errors:
        print(f"# ошибка источника: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
