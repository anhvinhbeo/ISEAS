#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from slugify import slugify
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BASE_URL = "https://www.iseas.edu.sg/library/blog/daily-news-alerts/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
RSS_DIR = "rss"
JSON_FILE = "data.json"
MAX_ARTICLES = 100   # giới hạn số bài crawl mỗi run
MAX_THREADS = 5

CATEGORIES = [
    "vietnam",
    "indonesia",
    "asean",
    "thailand",
    "philippines",
    "malaysia",
    "singapore",
    "myanmar",
    "laos",
]

# ----------------------
# HELPERS
# ----------------------
def get_links():
    """
    Crawl các link tin theo ngày, gom tất cả các bài
    """
    links = []
    for i in range(30):  # crawl 30 ngày gần nhất, tùy chỉnh
        date_str = (datetime.now() - timedelta(days=i)).strftime("%y%m%d")
        url = f"{BASE_URL}{date_str}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=5)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a"):
                href = a.get("href")
                if href and "/library/blog/daily-news-alerts/" in href:
                    links.append(href)
        except:
            continue
    return list(set(links))[:MAX_ARTICLES]


def get_fast_content(url):
    """
    Lấy nhanh nội dung bài, chỉ text, bỏ hình
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        texts = []
        for p in soup.find_all("p"):
            t = p.get_text(strip=True)
            if len(t) > 50:
                texts.append(t)
            if len(" ".join(texts)) > 1500:
                break
        return "\n".join(texts)
    except:
        return ""


def parse_article(url):
    """
    Lấy metadata cơ bản + content nhanh
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")

        title = soup.find("h1")
        title = title.get_text(strip=True) if title else "No Title"

        date = soup.find("time")
        if date and date.has_attr("datetime"):
            dt = datetime.fromisoformat(date["datetime"])
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        # content
        content = get_fast_content(url)
        return {
            "title": title,
            "link": url,
            "date": dt,
            "content": content,
        }
    except:
        return None


# ----------------------
# BUILD RSS
# ----------------------
def build(data):
    if not os.path.exists(RSS_DIR):
        os.makedirs(RSS_DIR)

    # 1. RSS theo từng category
    for cat, articles in data.items():
        fg = FeedGenerator()
        fg.title(f"ISEAS Daily News - {cat}")
        fg.link(href=BASE_URL)
        fg.description(f"Daily news alerts for {cat}")
        for it in articles:
            if not it:
                continue
            e = fg.add_entry()
            e.title(it["title"])
            e.link(href=it["link"])
            e.pubDate(it["date"])
            e.description(it["content"])
        fg.rss_file(f"{RSS_DIR}/{slugify(cat)}.xml")

    # 2. RSS gom tất cả theo category
    fg2 = FeedGenerator()
    fg2.title("ISEAS Daily News - All by Category")
    fg2.link(href=BASE_URL)
    fg2.description("All categories combined, sorted by category")
    for cat, articles in data.items():
        for it in articles:
            if not it:
                continue
            e = fg2.add_entry()
            e.title(f"[{cat}] {it['title']}")
            e.link(href=it["link"])
            e.pubDate(it["date"])
            e.description(it["content"])
    fg2.rss_file(f"{RSS_DIR}/all_by_category.xml")

    # 3. RSS gom tất cả theo date
    all_articles = []
    for cat, articles in data.items():
        all_articles.extend(articles)
    all_articles.sort(key=lambda x: x["date"], reverse=True)

    fg3 = FeedGenerator()
    fg3.title("ISEAS Daily News - All by Date")
    fg3.link(href=BASE_URL)
    fg3.description("All categories combined, sorted by date")
    for it in all_articles:
        if not it:
            continue
        e = fg3.add_entry()
        e.title(f"[{it['title']}]")
        e.link(href=it["link"])
        e.pubDate(it["date"])
        e.description(it["content"])
    fg3.rss_file(f"{RSS_DIR}/all_by_date.xml")


# ----------------------
# MAIN
# ----------------------
def main():
    links = get_links()

    data = {cat: [] for cat in CATEGORIES}

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
        futures = [ex.submit(parse_article, url) for url in links]
        for f in futures:
            res = f.result()
            if not res:
                continue
            # assign category
            for cat in CATEGORIES:
                if cat in res["link"]:
                    data[cat].append(res)
                    break

    # build RSS
    build(data)

    # save json
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, ensure_ascii=False)


if __name__ == "__main__":
    from datetime import timedelta
    main()