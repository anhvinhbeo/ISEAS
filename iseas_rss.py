import requests, os, json, time, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from feedgen.feed import FeedGenerator
from slugify import slugify
from newspaper import Article

BASE = "https://www.iseas.edu.sg/library/blog/daily-news-alerts/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CACHE = "rss/seen_links.json"

os.makedirs("rss", exist_ok=True)

def load_seen():
    if os.path.exists(CACHE):
        return set(json.load(open(CACHE)))
    return set()

def save_seen(seen):
    json.dump(list(seen), open(CACHE, "w"))

def clean(text):
    return text.replace("\n", " ").strip()

def normalize(cat):
    mapping = {
        "Viet Nam": "Vietnam",
        "U.S.": "United States",
        "US": "United States"
    }
    return mapping.get(cat.strip(), cat.strip())

# ===== SUMMARY =====
def get_summary(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta.get("content").strip()

        p = soup.find("p")
        if p:
            return p.get_text(strip=True)
    except:
        pass
    return ""

# ===== FULL TEXT =====
def get_full_content(url):
    try:
        article = Article(url)
        article.download()
        article.parse()

        text = article.text
        text = re.sub(r"\n+", "\n", text).strip()

        if len(text) > 4000:
            text = text[:4000] + "..."

        return text
    except:
        return ""

# ===== GET LINKS =====
def get_links(seen):
    links = []

    for p in range(1, 100):
        url = BASE if p == 1 else f"{BASE}page/{p}/"
        r = requests.get(url, headers=HEADERS)

        if r.status_code != 200:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        stop = False

        for a in soup.select("h2 a"):
            href = a.get("href")
            if not href:
                continue

            full = urljoin(BASE, href)

            if full in seen:
                stop = True
                break

            links.append(full)

        if stop:
            break

        time.sleep(0.3)

    return list(set(links))

# ===== PARSE =====
def parse(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        content = soup.select_one(".entry-content")
        if not content:
            return {}

        dstr = url.rstrip("/").split("/")[-1]
        try:
            d = datetime.strptime(dstr, "%y%m%d").replace(tzinfo=timezone.utc)
        except:
            d = datetime.now(timezone.utc)

        data = {}
        current = None

        for el in content.find_all(["h3", "h4", "p", "ul"]):

            if el.name in ["h3", "h4"]:
                current = normalize(el.get_text())
                data.setdefault(current, [])
                continue

            if current:
                for a in el.find_all("a", href=True):
                    link = urljoin(url, a["href"])
                    title = clean(a.get_text())

                    if not title or not link:
                        continue

                    summary = get_summary(link)
                    full_text = get_full_content(link)

                    data[current].append({
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "content": full_text,
                        "date": d
                    })

        return data

    except:
        return {}

# ===== CRAWL =====
def crawl(links):
    all_data = {}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(parse, l) for l in links]

        for f in as_completed(futures):
            res = f.result()

            for k, v in res.items():
                all_data.setdefault(k, []).extend(v)

    return all_data

# ===== BUILD RSS =====
def build(all_data):

    # --- CATEGORY (SUMMARY) ---
    for cat, items in all_data.items():
        fg = FeedGenerator()
        fg.title(f"ISEAS - {cat}")
        fg.link(href=BASE)
        fg.description(f"News about {cat}")

        seen = set()

        for it in items:
            title = it.get("title","").strip()
            link = it.get("link","").strip()
            summary = it.get("summary","")

            if not title or not link or link in seen:
                continue

            seen.add(link)

            e = fg.add_entry()
            e.title(title)
            e.link(href=link)
            e.pubDate(it["date"])
            e.description(summary if summary else title)

        fg.rss_file(f"rss/{slugify(cat)}.xml")

    # --- ALL BY CATEGORY (SUMMARY) ---
    fg = FeedGenerator()
    fg.title("ISEAS - All by Category")
    fg.link(href=BASE)
    fg.description("All grouped")

    for cat, items in all_data.items():
        for it in items:
            title = it.get("title","").strip()
            link = it.get("link","").strip()
            summary = it.get("summary","")

            if not title or not link:
                continue

            e = fg.add_entry()
            e.title(f"[{cat}] {title}")
            e.link(href=link)
            e.pubDate(it["date"])
            e.description(summary if summary else title)

    fg.rss_file("rss/all_by_category.xml")

    # --- ALL BY DATE (FULL TEXT) ---
    fg = FeedGenerator()
    fg.title("ISEAS - All by Date")
    fg.link(href=BASE)
    fg.description("Full text feed")

    all_items = []
    for v in all_data.values():
        all_items.extend(v)

    all_items.sort(key=lambda x: x["date"], reverse=True)

    seen = set()

    for it in all_items:
        title = it.get("title","").strip()
        link = it.get("link","").strip()
        content = it.get("content","")

        if not title or not link or link in seen:
            continue

        seen.add(link)

        e = fg.add_entry()
        e.title(title)
        e.link(href=link)
        e.pubDate(it["date"])

        text = f"{title}\n\n{content}" if content else title
        e.description(text)

    fg.rss_file("rss/all_by_date.xml")

# ===== MAIN =====
def main():
    seen = load_seen()
    links = get_links(seen)
    print("New:", len(links))

    data = crawl(links)
    build(data)

    seen.update(links)
    save_seen(seen)

    print("DONE")

if __name__ == "__main__":
    main()