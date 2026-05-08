# SerpApi — Google Scholar API Reference

> **Source:** https://serpapi.com/google-scholar-api  
> **Playground:** https://serpapi.com/playground?engine=google_scholar  
> **Requires:** A SerpApi API key — https://serpapi.com/users/sign_up  
> Cached searches are free and not counted toward your monthly quota. Cache expires after 1 hour.

---

## Base Endpoint

```
GET https://serpapi.com/search
```

All requests must include `engine=google_scholar` and `api_key=YOUR_KEY`.

---

## Parameters

### Required

| Parameter | Description |
|-----------|-------------|
| `engine`  | Must be `google_scholar` |
| `api_key` | Your SerpApi private key |
| `q`       | Search query string. Supports `author:` and `source:` helpers. Optional only when `cites` is used alone. |

### Search Query Helpers (inside `q`)

```
author:Hinton              # search by author name
source:Nature              # search by publication source
"attention is all you need" # exact phrase
```

### Advanced Scholar Parameters

| Parameter  | Type   | Description |
|------------|--------|-------------|
| `cites`    | string | Unique article ID — triggers "Cited By" search. Use with `q` to search *within* citing articles. Incompatible with `cluster`. Example: `cites=1275980731835430123` |
| `as_ylo`   | int    | Year lower bound — exclude results before this year (e.g. `2020`) |
| `as_yhi`   | int    | Year upper bound — exclude results after this year (e.g. `2024`) |
| `scisbd`   | int    | Sort recently-added articles by date: `1` = abstracts only, `2` = everything. Default `0` = sort by relevance |
| `cluster`  | string | Unique article ID — triggers "All Versions" search. Use alone; incompatible with `q`+`cites`. Example: `cluster=1275980731835430123` |

### Localization

| Parameter | Description |
|-----------|-------------|
| `hl`      | Interface language. Two-letter code (e.g. `en`, `fr`, `de`). See [Google languages](https://serpapi.com/google-languages) |
| `lr`      | Limit results to specific languages. Format: `lang_en\|lang_fr`. See [Google lr languages](https://serpapi.com/google-lr-languages) |

### Pagination

| Parameter | Default | Range   | Description |
|-----------|---------|---------|-------------|
| `start`   | `0`     | 0+      | Result offset (0-based). Page 2 = `10`, page 3 = `20`, etc. |
| `num`     | `10`    | 1–20    | Number of results per page |

### Search Type (`as_sdt`)

| Value      | Behavior |
|------------|----------|
| `0`        | Articles only, patents excluded (default) |
| `7`        | Articles + patents included |
| `4`        | Case law — US courts only (all State + Federal) |
| `4,33,192` | Case law with specific courts (`4` is required first; courts separated by commas) |

For a full list of court codes: https://serpapi.com/google-scholar-courts

### Advanced Filters

| Parameter | Values        | Description |
|-----------|---------------|-------------|
| `safe`    | `active`, `off` | Adult content filtering |
| `filter`  | `1` (default), `0` | Toggle "Similar Results" and "Omitted Results" filters |
| `as_vis`  | `0` (default), `1` | `1` = exclude citation entries from results |
| `as_rr`   | `0` (default), `1` | `1` = show only review articles |

### SerpApi Control Parameters

| Parameter    | Default  | Description |
|--------------|----------|-------------|
| `no_cache`   | `false`  | `true` = force a fresh fetch, bypassing cache. Do not combine with `async` |
| `async`      | `false`  | `true` = submit search and retrieve later via [Search Archive API](https://serpapi.com/search-archive-api). Do not combine with `no_cache` |
| `zero_trace` | `false`  | Enterprise only. Skips storing search parameters/files/metadata on SerpApi servers |
| `output`     | `json`   | `json` for structured data, `html` for raw HTML |

---

## Example Queries

```bash
# Basic keyword search
https://serpapi.com/search?engine=google_scholar&q=transformer+neural+network&api_key=KEY

# Search by author
https://serpapi.com/search?engine=google_scholar&q=author:Hinton+deep+learning&api_key=KEY

# Filter by year range
https://serpapi.com/search?engine=google_scholar&q=LLVM+compiler&as_ylo=2020&as_yhi=2024&api_key=KEY

# Sort by recency (recent articles first)
https://serpapi.com/search?engine=google_scholar&q=MLIR&scisbd=2&api_key=KEY

# Cited-by lookup (articles citing a specific paper)
https://serpapi.com/search?engine=google_scholar&cites=1275980731835430123&api_key=KEY

# Cited-by + query filter (search within citing articles)
https://serpapi.com/search?engine=google_scholar&q=attention+mechanism&cites=3387547533016043281&api_key=KEY

# All versions of an article
https://serpapi.com/search?engine=google_scholar&cluster=1275980731835430123&api_key=KEY

# Include patents
https://serpapi.com/search?engine=google_scholar&q=GPU+architecture&as_sdt=7&api_key=KEY

# Case law (US courts)
https://serpapi.com/search?engine=google_scholar&q=machine+learning&as_sdt=4&api_key=KEY

# Pagination — page 3
https://serpapi.com/search?engine=google_scholar&q=CUDA+optimization&start=20&num=10&api_key=KEY

# Limit to French-language results
https://serpapi.com/search?engine=google_scholar&q=apprentissage+automatique&lr=lang_fr&hl=fr&api_key=KEY

# Exclude citation entries
https://serpapi.com/search?engine=google_scholar&q=reinforcement+learning&as_vis=1&api_key=KEY

# Review articles only
https://serpapi.com/search?engine=google_scholar&q=large+language+models&as_rr=1&api_key=KEY
```

---

## Response Structure

### Top-Level Keys

```json
{
  "search_metadata": { ... },
  "search_parameters": { ... },
  "search_information": { ... },
  "citations_per_year": [ ... ],   // present for cites searches
  "profiles": { ... },              // present for cites searches
  "organic_results": [ ... ],
  "related_searches": [ ... ],
  "pagination": { ... },
  "serpapi_pagination": { ... }
}
```

### `search_metadata`

```json
{
  "id": "5d8cb082de983409f4a1aa21",
  "status": "Success",              // "Processing" → "Success" | "Error"
  "json_endpoint": "https://serpapi.com/searches/.../....json",
  "created_at": "2019-09-26 12:35:14 UTC",
  "processed_at": "2019-09-26 12:35:14 UTC",
  "google_scholar_url": "https://scholar.google.com/scholar?...",
  "raw_html_file": "https://serpapi.com/searches/.../....html",
  "total_time_taken": 1.24
}
```

### `search_information`

```json
{
  "total_results": 5880000,
  "time_taken_displayed": 0.06,
  "query_displayed": "biology"
}
```

### `organic_results` — Article Entry

```json
{
  "position": 0,
  "title": "Article Title",
  "result_id": "JC4Acibs_4kJ",          // used for cite lookups
  "link": "https://...",                 // external article URL (may be absent)
  "snippet": "Abstract preview text...",
  "type": "Html",                        // present if HTML version available
  "publication_info": {
    "summary": "Authors - Journal, Year - publisher.com",
    "authors": [
      {
        "name": "Author Name",
        "link": "https://scholar.google.com/citations?user=...",
        "author_id": "XXXXXXXX",
        "serpapi_scholar_link": "https://serpapi.com/search.json?author_id=...&engine=google_scholar_author"
      }
    ]
  },
  "resources": [
    {
      "title": "publisher.com",
      "file_format": "PDF",             // "PDF" | "HTML"
      "link": "https://..."
    }
  ],
  "inline_links": {
    "serpapi_cite_link": "https://serpapi.com/search.json?engine=google_scholar_cite&q=JC4Acibs_4kJ",
    "html_version": "https://...",      // if HTML version available
    "cited_by": {
      "total": 14003,
      "link": "https://scholar.google.com/scholar?cites=...",
      "cites_id": "9943926152122871332",
      "serpapi_scholar_link": "https://serpapi.com/search.json?cites=...&engine=google_scholar"
    },
    "related_pages_link": "https://scholar.google.com/scholar?q=related:...",
    "serpapi_related_pages_link": "https://serpapi.com/search.json?...&engine=google_scholar",
    "versions": {
      "total": 6,
      "link": "https://scholar.google.com/scholar?cluster=...",
      "cluster_id": "9943926152122871332",
      "serpapi_scholar_link": "https://serpapi.com/search.json?cluster=...&engine=google_scholar"
    },
    "cached_page_link": "https://scholar.googleusercontent.com/scholar?q=cache:..."
  }
}
```

### `organic_results` — Case Law Entry (when `as_sdt=4`)

```json
{
  "position": 1,
  "title": "Case Name v. Defendant",
  "result_id": "cuz3eYJiNogJ",
  "link": "https://scholar.google.com/scholar_case?case=...",
  "case_id": "9815140750432136306",
  "serpapi_scholar_case_law_link": "https://serpapi.com/search.json?case_id=...&engine=google_scholar_case_law",
  "snippet": "...",
  "publication_info": {
    "summary": "772 F. 3d 709 - Court of Appeals, Federal Circuit, 2014"
  },
  "inline_links": { ... }
}
```

### `citations_per_year` (only in `cites` searches)

```json
[
  { "year": 2020, "citations": 45 },
  { "year": 2021, "citations": 112 },
  { "year": 2022, "citations": 230 }
]
```

### `pagination`

```json
{
  "current": 1,
  "next": "https://scholar.google.com/scholar?start=10&...",
  "other_pages": {
    "2": "https://scholar.google.com/scholar?start=10&...",
    "3": "https://scholar.google.com/scholar?start=20&..."
  }
}
```

Use `serpapi_pagination` for SerpApi-native pagination links.

---

## Related Engines

| Engine | Use Case | Docs |
|--------|----------|------|
| `google_scholar_cite` | Get formatted citations for an article by `result_id` | https://serpapi.com/google-scholar-cite-api |
| `google_scholar_author` | Fetch an author's profile, articles, and co-authors by `author_id` | https://serpapi.com/google-scholar-author-api |
| `google_scholar_case_law` | Fetch full case law details by `case_id` | https://serpapi.com/google-scholar-case-law-api |

### Citation Lookup Example

Use the `result_id` from any organic result to fetch all citation formats:

```
https://serpapi.com/search.json?engine=google_scholar_cite&q=JC4Acibs_4kJ&api_key=KEY
```

Returns MLA, APA, Chicago, Harvard, and Vancouver formats.

---

## Python Example

### Minimal fetch

```python
import requests

params = {
    "engine": "google_scholar",
    "q": "attention is all you need",
    "api_key": "YOUR_API_KEY",
}

response = requests.get("https://serpapi.com/search", params=params)
data = response.json()

for result in data.get("organic_results", []):
    print(result["title"])
    print(result.get("link", "No link"))
    print(result["publication_info"]["summary"])
    print()
```

### Using the official `google-search-results` library

```bash
pip install google-search-results
```

```python
from serpapi import GoogleSearch

params = {
    "engine": "google_scholar",
    "q": "transformer architecture GPU",
    "as_ylo": 2020,
    "num": 10,
    "api_key": "YOUR_API_KEY",
}

search = GoogleSearch(params)
results = search.get_dict()

for r in results.get("organic_results", []):
    title = r["title"]
    cited_by = r.get("inline_links", {}).get("cited_by", {}).get("total", 0)
    pub = r.get("publication_info", {}).get("summary", "")
    print(f"[{cited_by} citations] {title}")
    print(f"  → {pub}\n")
```

### Pagination helper

```python
import time
from serpapi import GoogleSearch

def fetch_all_results(query: str, api_key: str, max_pages: int = 5) -> list:
    results = []
    for page in range(max_pages):
        params = {
            "engine": "google_scholar",
            "q": query,
            "start": page * 10,
            "num": 10,
            "api_key": api_key,
        }
        data = GoogleSearch(params).get_dict()
        batch = data.get("organic_results", [])
        if not batch:
            break
        results.extend(batch)
        total = int(data.get("search_information", {}).get("total_results", 0))
        if (page + 1) * 10 >= total:
            break
        time.sleep(2)  # be polite to the API
    return results
```

### Cited-by chain (follow citations)

```python
from serpapi import GoogleSearch

def get_citing_papers(cites_id: str, api_key: str) -> list:
    params = {
        "engine": "google_scholar",
        "cites": cites_id,
        "num": 10,
        "api_key": api_key,
    }
    data = GoogleSearch(params).get_dict()
    return data.get("organic_results", [])

# Get the cites_id from an organic result first, then:
citing = get_citing_papers("9943926152122871332", "YOUR_API_KEY")
for paper in citing:
    print(paper["title"])
```

---

## Key ID Types

| ID Field          | Source                          | Used In                         |
|-------------------|---------------------------------|---------------------------------|
| `result_id`       | `organic_results[n].result_id`  | `engine=google_scholar_cite`    |
| `cites_id`        | `inline_links.cited_by.cites_id`| `cites=` parameter              |
| `cluster_id`      | `inline_links.versions.cluster_id` | `cluster=` parameter         |
| `author_id`       | `publication_info.authors[n].author_id` | `engine=google_scholar_author` |
| `case_id`         | `organic_results[n].case_id`    | `engine=google_scholar_case_law` |

---

## Error Handling

Check `search_metadata.status`:

```python
data = search.get_dict()

if data.get("search_metadata", {}).get("status") != "Success":
    print("Error:", data.get("error"))
else:
    results = data.get("organic_results", [])
```

Common issues: invalid `api_key`, malformed parameters, or exhausted monthly quota. Check account status at https://serpapi.com/dashboard.

---

## Notes & Gotchas

- `cluster` cannot be combined with `q` and `cites` together — use it alone.
- `async` and `no_cache` must not be used together.
- `num` is capped at **20** per request. Paginate with `start` for more.
- `total_results` in `search_information` is an estimate from Google Scholar, not exact.
- Cached results (within 1h window) are **free** and don't count against quota — avoid `no_cache=true` in production loops.
- For bulk scraping, async mode + [Search Archive API](https://serpapi.com/search-archive-api) is more efficient.