"""
Fintech Daily Digest — GitHub Action generator (no AI, keyword-based tagging)
Fetches RSS feeds, tags articles by topic and geography, writes index.html
"""

import urllib.request
import xml.etree.ElementTree as ET
import json
import re
import gzip
from datetime import datetime, timezone, timedelta

# ── Feed configuration ──────────────────────────────────────────────────────
FEEDS = [
    {"url": "https://www.finextra.com/rss/headlines.aspx", "source": "Finextra",        "hours": 48,  "max": 5},
    {"url": "https://sifted.eu/feed/",                     "source": "Sifted",           "hours": 48,  "max": 4},
    {"url": "https://www.bankingdive.com/feeds/news/",     "source": "Banking Dive",     "hours": 48,  "max": 4},
    {"url": "https://tearsheet.co/feed/",                  "source": "Tearsheet",        "hours": 48,  "max": 3},
    {"url": "https://medium.com/feed/tag/fintech",         "source": "Medium / Fintech", "hours": 24,  "max": 3},
    {"url": "https://medium.com/feed/wharton-fintech",     "source": "Wharton Fintech",  "hours": 720, "max": 2},
]

# ── Topic keyword rules ──────────────────────────────────────────────────────
TOPIC_RULES = {
    "Payments": [
        "payment", "payments", "pay-by-bank", "pay by bank", "checkout", "remittance",
        "remittances", "transfer", "transfers", "transaction", "transactions", "acquiring",
        "pos ", "point of sale", "p2p", "open banking", "zelle", "paypal", "stripe",
        "adyen", "klarna", "visa", "mastercard", "swift", "sepa", "wire",
    ],
    "Crypto": [
        "crypto", "cryptocurrency", "bitcoin", "ethereum", "blockchain", "defi",
        "decentralised finance", "decentralized finance", "nft", "web3", "on-chain",
        "onchain", "digital asset", "coinbase", "binance", "ftx", "bankman-fried",
        "canton network", "wallet", "token ", "tokenomics",
    ],
    "Stablecoins": [
        "stablecoin", "stablecoins", "cbdc", "tokenised deposit", "tokenized deposit",
        "digital dollar", "digital currency", "usdc", "usdt", "tether",
        "programmable money", "e-money",
    ],
    "AI & Agentic": [
        "artificial intelligence", " ai ", "ai-powered", "ai adoption", "machine learning",
        "agentic", "llm", "large language model", "generative ai", "genai", "chatgpt",
        "hallucination", "neural network", "deep learning", "copilot", "automation",
    ],
    "Banking": [
        "bank", "banking", "neobank", "neobanks", "lender", "lending", "credit",
        "deposit", "deposits", "savings", "loan", "loans", "mortgage", "account",
        "banking license", "banking licence", "retail bank", "core banking",
        "unicorn", "fintech", "wealth management", "asset management",
    ],
}

# ── Geography keyword rules ──────────────────────────────────────────────────
GEO_RULES = [
    ("🇺🇸 US",          ["united states", " u.s.", "u.s. ", "american", "federal reserve", "sec ", "cfpb", "fdic", "us bank", "us-based", "new york", "silicon valley"]),
    ("🇬🇧 UK",          ["united kingdom", " u.k.", "u.k. ", "british", "england", "fca ", "barclays", "lloyds", "hsbc", "natwest", "monzo", "revolut", "truelayer", "london"]),
    ("🇪🇺 Europe",      ["european union", " eu ", "eu-", "ecb ", "euro zone", "eurozone", "eba "]),
    ("🇩🇪 Germany",     ["germany", "german", "deutsche", "berlin"]),
    ("🇫🇷 France",      ["france", "french", "paris"]),
    ("🇮🇹 Italy",       ["italy", "italian", "satispay", "milan"]),
    ("🇳🇱 Netherlands", ["netherlands", "dutch", "amsterdam", "adyen"]),
    ("🇸🇬 Singapore",   ["singapore", "mas ", "monetary authority of singapore"]),
    ("🇨🇦 Canada",      ["canada", "canadian", "koho", "toronto"]),
    ("🇦🇺 Australia",   ["australia", "australian", "sydney", "apra"]),
    ("🇮🇳 India",       ["india", "indian", "mumbai", "rbi "]),
    ("🇧🇷 Brazil",      ["brazil", "brazilian", "nubank", "são paulo"]),
    ("🇦🇪 UAE",         ["uae", "dubai", "abu dhabi", "united arab"]),
]
GLOBAL_KEYWORDS = ["g7", "g20", "imf", "bis ", "world bank", "global", "cross-border", "international", "worldwide", "multinational"]


def fetch_feed(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FintechDigest/1.0)",
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw_bytes = resp.read()
        content_encoding = resp.headers.get("Content-Encoding", "")
    # Decompress gzip if needed
    if "gzip" in content_encoding:
        raw_bytes = gzip.decompress(raw_bytes)
    else:
        # Try gzip anyway in case server omitted the header
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except Exception:
            pass
    raw = raw_bytes.decode("utf-8", errors="replace")
    # Strip preamble before XML
    match = re.search(r"<(\?xml|rss|feed|channel)", raw)
    if not match:
        return None
    return raw[match.start():]


def parse_date(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def get_tags(title, desc):
    haystack = (title + " " + desc).lower()
    tags = []
    for topic, keywords in TOPIC_RULES.items():
        if any(kw in haystack for kw in keywords):
            tags.append(topic)
    return tags


def get_geography(title, desc):
    haystack = (title + " " + desc).lower()
    # Check global first
    if any(kw in haystack for kw in GLOBAL_KEYWORDS):
        # But still check for a dominant single country
        pass
    for geo, keywords in GEO_RULES:
        if any(kw in haystack for kw in keywords):
            return geo
    if any(kw in haystack for kw in GLOBAL_KEYWORDS):
        return "🌍 Global"
    return "🌍 Global"


def parse_feed(xml_str, source, hours, max_items):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    articles = []

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Detect RSS vs Atom
    items = root.findall(".//item") or root.findall(".//atom:entry", ns) or root.findall(".//entry")

    for item in items:
        if len(articles) >= max_items:
            break

        def text(tag, alt=None):
            el = item.find(tag) or (item.find(f"atom:{tag}", ns) if alt else None)
            return (el.text or "").strip() if el is not None else ""

        title = text("title")
        link = text("link")
        # Atom link may be in href attribute
        if not link:
            link_el = item.find("link") or item.find("atom:link", ns)
            if link_el is not None:
                link = link_el.get("href", "")

        raw_desc = text("description") or text("summary") or text("content")
        description = strip_html(raw_desc)

        raw_date = text("pubDate") or text("published") or text("updated")
        pub_dt = parse_date(raw_date)

        if pub_dt and pub_dt < cutoff:
            continue
        if not title or not link:
            continue

        tags = get_tags(title, description)
        geography = get_geography(title, description)

        articles.append({
            "title": title,
            "description": description,
            "link": link,
            "pubDate": pub_dt.strftime("%a, %d %b %Y %H:%M:%S GMT") if pub_dt else "",
            "source": source,
            "geography": geography,
            "tags": tags,
            "summary": None,
            "key_stat": None,
            "key_quote": None,
            "key_quote_attr": None,
        })

    return articles


def build_html(articles, date_str, feed_names):
    digest_data = {
        "date": date_str,
        "feeds": feed_names,
        "articles": articles,
    }
    json_str = json.dumps(digest_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fintech Daily Digest</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8f9fb; --surface: #fff; --border: #e5e7eb;
      --text: #111827; --muted: #6b7280; --accent: #2563eb;
      --stat-bg: #f0fdf4; --stat-border: #86efac; --stat-text: #15803d;
      --quote-bg: #fafafa; --tag-bg: #f1f5f9; --tag-text: #475569;
      --geo-bg: #eff6ff; --geo-text: #1d4ed8;
      --topic-bg: #fef3c7; --topic-text: #92400e;
      --warn-bg: #fffbeb; --warn-text: #92400e;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); min-height: 100vh; }}
    .header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
    .header-left {{ display: flex; align-items: center; gap: 10px; }}
    .logo {{ width: 30px; height: 30px; background: var(--accent); border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 15px; }}
    .header h1 {{ font-size: 16px; font-weight: 700; letter-spacing: -0.3px; }}
    .header-sub {{ font-size: 11px; color: var(--muted); margin-top: 1px; }}
    .filter-bar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 7px 20px; display: flex; flex-direction: column; gap: 6px; }}
    .filter-row {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
    .filter-label {{ font-size: 10px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-right: 2px; min-width: 58px; }}
    .filter-pill {{ padding: 3px 11px; border-radius: 20px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid var(--border); background: none; color: var(--muted); transition: all 0.15s; }}
    .filter-pill:hover {{ background: var(--tag-bg); color: var(--text); }}
    .filter-pill.active-source {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .filter-pill.active-geo {{ background: var(--geo-text); color: #fff; border-color: var(--geo-text); }}
    .filter-pill.active-topic {{ background: #92400e; color: #fff; border-color: #92400e; }}
    .main {{ max-width: 760px; margin: 0 auto; padding: 20px 16px; }}
    .digest-meta {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }}
    .digest-count {{ font-size: 12px; color: var(--muted); }}
    .digest-date-badge {{ font-size: 11px; padding: 2px 8px; background: var(--warn-bg); color: var(--warn-text); border-radius: 99px; font-weight: 500; }}
    .articles {{ display: flex; flex-direction: column; gap: 14px; }}
    .article-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px; transition: box-shadow 0.15s; }}
    .article-card:hover {{ box-shadow: 0 3px 10px rgba(0,0,0,0.07); }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }}
    .card-tags {{ display: flex; gap: 5px; align-items: center; flex-wrap: wrap; flex: 1; }}
    .source-tag {{ padding: 2px 9px; background: var(--tag-bg); color: var(--tag-text); border-radius: 5px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .geo-tag {{ padding: 2px 9px; background: var(--geo-bg); color: var(--geo-text); border-radius: 5px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .topic-tag {{ padding: 2px 9px; background: var(--topic-bg); color: var(--topic-text); border-radius: 5px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
    .pub-date {{ font-size: 11px; color: var(--muted); white-space: nowrap; flex-shrink: 0; }}
    .article-title {{ font-size: 14px; font-weight: 700; line-height: 1.4; margin-bottom: 7px; }}
    .article-title a {{ color: inherit; text-decoration: none; }}
    .article-title a:hover {{ color: var(--accent); }}
    .article-desc {{ font-size: 13px; color: #374151; line-height: 1.6; margin-bottom: 12px; }}
    .card-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 11px; border-top: 1px solid var(--border); }}
    .source-link {{ font-size: 12px; color: var(--accent); text-decoration: none; font-weight: 500; }}
    .source-link:hover {{ text-decoration: underline; }}
    .source-cite {{ font-size: 11px; color: var(--muted); }}
    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 99px; }}
  </style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="logo">📰</div>
    <div>
      <h1>Fintech Daily Digest</h1>
      <div class="header-sub" id="headerSub">Updated daily</div>
    </div>
  </div>
</div>
<div class="filter-bar" id="filterBar" style="display:none">
  <div class="filter-row">
    <span class="filter-label">Source</span>
    <button class="filter-pill active-source" data-type="source" data-value="all" onclick="setFilter('source','all',this)">All</button>
    <span id="sourcePills"></span>
  </div>
  <div class="filter-row">
    <span class="filter-label">Topic</span>
    <button class="filter-pill active-topic" data-type="topic" data-value="all" onclick="setFilter('topic','all',this)">All</button>
    <span id="topicPills"></span>
  </div>
  <div class="filter-row">
    <span class="filter-label">Geography</span>
    <button class="filter-pill active-geo" data-type="geo" data-value="all" onclick="setFilter('geo','all',this)">All</button>
    <span id="geoPills"></span>
  </div>
</div>
<div class="main" id="main"></div>
<!-- DIGEST DATA -->
<script>
window.DIGEST_DATA = {json_str};
</script>
<script>
const TOPIC_ORDER = ["Payments","Crypto","Stablecoins","AI & Agentic","Banking"];
let activeSource='all', activeGeo='all', activeTopic='all';
const data = window.DIGEST_DATA;
function init() {{
  if (!data.date || !data.articles.length) {{
    document.getElementById('main').innerHTML = '<div style="text-align:center;padding:48px 32px;background:#fff;border:1px solid #e5e7eb;border-radius:12px"><div style="font-size:36px;margin-bottom:14px">⏰</div><div style="font-size:15px;font-weight:600;margin-bottom:8px">No articles today</div></div>';
    return;
  }}
  document.getElementById('headerSub').textContent = 'Last updated: ' + data.date;
  const sources = [...new Set(data.articles.map(a => a.source))];
  document.getElementById('sourcePills').innerHTML = sources.map(s => `<button class="filter-pill" data-type="source" data-value="${{esc(s)}}" onclick="setFilter('source','${{esc(s)}}',this)">${{esc(s)}}</button>`).join('');
  const allTopics = new Set(data.articles.flatMap(a => a.tags || []));
  const topics = TOPIC_ORDER.filter(t => allTopics.has(t));
  document.getElementById('topicPills').innerHTML = topics.map(t => `<button class="filter-pill" data-type="topic" data-value="${{esc(t)}}" onclick="setFilter('topic','${{esc(t)}}',this)">${{esc(t)}}</button>`).join('');
  const geos = [...new Set(data.articles.map(a => a.geography).filter(Boolean))].sort((a,b) => {{ if(a==='🌍 Global') return 1; if(b==='🌍 Global') return -1; return a.localeCompare(b); }});
  document.getElementById('geoPills').innerHTML = geos.map(g => `<button class="filter-pill" data-type="geo" data-value="${{esc(g)}}" onclick="setFilter('geo','${{esc(g)}}',this)">${{esc(g)}}</button>`).join('');
  document.getElementById('filterBar').style.display = 'flex';
  render();
}}
function render() {{
  let visible = data.articles;
  if (activeSource !== 'all') visible = visible.filter(a => a.source === activeSource);
  if (activeTopic !== 'all') visible = visible.filter(a => (a.tags || []).includes(activeTopic));
  if (activeGeo !== 'all') visible = visible.filter(a => a.geography === activeGeo);
  document.getElementById('main').innerHTML =
    `<div class="digest-meta"><div class="digest-count">${{visible.length}} article${{visible.length !== 1 ? 's' : ''}}</div><span class="digest-date-badge">${{data.date}}</span></div>` +
    `<div class="articles">${{visible.map(buildCard).join('')}}</div>`;
}}
function buildCard(a) {{
  const date = a.pubDate ? fmtRel(new Date(a.pubDate)) : '';
  const geo = a.geography ? `<span class="geo-tag">${{esc(a.geography)}}</span>` : '';
  const topics = (a.tags || []).map(t => `<span class="topic-tag">${{esc(t)}}</span>`).join('');
  return `<div class="article-card">
    <div class="card-top">
      <div class="card-tags"><span class="source-tag">${{esc(a.source)}}</span>${{geo}}${{topics}}</div>
      ${{date ? `<span class="pub-date">${{date}}</span>` : ''}}
    </div>
    <div class="article-title"><a href="${{esc(a.link)}}" target="_blank" rel="noopener">${{esc(a.title)}}</a></div>
    ${{a.description ? `<div class="article-desc">${{esc(a.description)}}</div>` : ''}}
    <div class="card-footer">
      <a class="source-link" href="${{esc(a.link)}}" target="_blank" rel="noopener">Read full article ↗</a>
      <span class="source-cite">Source: ${{esc(a.source)}}${{date ? ' · ' + date : ''}}</span>
    </div>
  </div>`;
}}
function setFilter(type, value, el) {{
  if (type === 'source') {{ activeSource = value; document.querySelectorAll('[data-type="source"]').forEach(p => p.classList.remove('active-source')); el.classList.add('active-source'); }}
  else if (type === 'topic') {{ activeTopic = value; document.querySelectorAll('[data-type="topic"]').forEach(p => p.classList.remove('active-topic')); el.classList.add('active-topic'); }}
  else {{ activeGeo = value; document.querySelectorAll('[data-type="geo"]').forEach(p => p.classList.remove('active-geo')); el.classList.add('active-geo'); }}
  render();
}}
function esc(s) {{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
function fmtRel(d) {{ const h = Math.floor((Date.now()-d.getTime())/3600000); if(h<1) return 'Just now'; if(h<24) return h+'h ago'; return Math.floor(h/24)+'d ago'; }}
init();
</script>
</body>
</html>"""


def main():
    all_articles = []
    feed_names = []

    for feed in FEEDS:
        print(f"Fetching {feed['source']}...")
        try:
            xml_str = fetch_feed(feed["url"])
            if not xml_str:
                print(f"  Skipped (no XML found)")
                continue
            articles = parse_feed(xml_str, feed["source"], feed["hours"], feed["max"])
            print(f"  Got {len(articles)} articles")
            all_articles.extend(articles)
            if articles:
                feed_names.append(feed["source"])
        except Exception as e:
            print(f"  Error: {e}")

    date_str = datetime.now(timezone.utc).strftime("%A %d %B %Y")
    html = build_html(all_articles, date_str, feed_names)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone — {len(all_articles)} articles written to index.html")


if __name__ == "__main__":
    main()
