# arXiv API — Basic Usage Reference

> **Source:** https://info.arxiv.org/help/api/user-manual.html  
> **Terms of Use:** https://info.arxiv.org/help/api/tou.html  
> Review terms before use. Cache results — search results only update once per day (midnight).

---

## Base URL

```
http://export.arxiv.org/api/query?{parameters}
```

Supports both **HTTP GET** (params in URL) and **HTTP POST** (params in header).

---

## Query Parameters

| Parameter      | Type                    | Default | Required |
|----------------|-------------------------|---------|----------|
| `search_query` | string                  | None    | No       |
| `id_list`      | comma-delimited string  | None    | No       |
| `start`        | int (0-based index)     | 0       | No       |
| `max_results`  | int                     | 10      | No       |
| `sortBy`       | string                  | —       | No       |
| `sortOrder`    | string                  | —       | No       |

### `search_query` vs `id_list` Logic

| `search_query` | `id_list` | Returns                                              |
|----------------|-----------|------------------------------------------------------|
| ✅             | ❌        | Articles matching the search query                   |
| ❌             | ✅        | Articles with IDs in `id_list`                       |
| ✅             | ✅        | Articles in `id_list` that *also* match the query    |

### Sorting

```
sortBy    = "relevance" | "lastUpdatedDate" | "submittedDate"
sortOrder = "ascending" | "descending"
```

---

## Search Query Construction

Fields are targeted with a `prefix:term` syntax.

| Prefix | Field              |
|--------|--------------------|
| `ti`   | Title              |
| `au`   | Author             |
| `abs`  | Abstract           |
| `co`   | Comment            |
| `jr`   | Journal Reference  |
| `cat`  | Subject Category   |
| `rn`   | Report Number      |
| `id`   | ID (prefer `id_list` instead) |
| `all`  | All fields         |

### Boolean Operators

```
AND      ANDNOT      OR
```

### URL Encoding

| Symbol        | Encoded | Use                                |
|---------------|---------|------------------------------------|
| space         | `+`     | Separate terms                     |
| `"`           | `%22`   | Phrase grouping                    |
| `(` / `)`     | `%28` / `%29` | Boolean grouping             |

### Date Filter

Filter by submission date with `submittedDate` (GMT, 24h format):

```
submittedDate:[YYYYMMDDTTTT+TO+YYYYMMDDTTTT]
```

---

## Example Queries

```bash
# Keyword in any field
http://export.arxiv.org/api/query?search_query=all:electron

# Boolean AND
http://export.arxiv.org/api/query?search_query=all:electron+AND+all:proton

# Author search
http://export.arxiv.org/api/query?search_query=au:del_maestro

# Author AND title keyword
http://export.arxiv.org/api/query?search_query=au:del_maestro+AND+ti:checkerboard

# Author ANDNOT title keyword
http://export.arxiv.org/api/query?search_query=au:del_maestro+ANDNOT+ti:checkerboard

# Phrase in title
http://export.arxiv.org/api/query?search_query=au:del_maestro+AND+ti:%22quantum+criticality%22

# Grouped Boolean
http://export.arxiv.org/api/query?search_query=au:del_maestro+ANDNOT+%28ti:checkerboard+OR+ti:Pyrochlore%29

# By arXiv ID
http://export.arxiv.org/api/query?id_list=cond-mat/0207270

# Specific version
http://export.arxiv.org/api/query?id_list=cond-mat/0207270v1

# Sort by date descending
http://export.arxiv.org/api/query?search_query=ti:%22electron+thermal+conductivity%22&sortBy=lastUpdatedDate&sortOrder=descending

# Date range filter
https://export.arxiv.org/api/query?search_query=au:del_maestro+AND+submittedDate:[202301010600+TO+202401010600]
```

---

## Paging

```bash
# Page 1: results 0–9
http://export.arxiv.org/api/query?search_query=all:electron&start=0&max_results=10

# Page 2: results 10–19
http://export.arxiv.org/api/query?search_query=all:electron&start=10&max_results=10
```

**Limits:**
- Max `max_results` per call: **2000**
- Max total retrievable: **30000** (HTTP 400 if exceeded)
- Add a **3-second delay** between consecutive calls

---

## Response Format

The API returns **Atom 1.0 XML**. Key feed-level elements:

```xml
<feed>
  <title>...</title>                         <!-- canonicalized query -->
  <id>...</id>                               <!-- unique query ID -->
  <updated>...</updated>                     <!-- midnight of today (cached) -->
  <link rel="self" .../>                     <!-- GET-retrievable URL -->
  <opensearch:totalResults>...</opensearch:totalResults>
  <opensearch:startIndex>...</opensearch:startIndex>
  <opensearch:itemsPerPage>...</opensearch:itemsPerPage>

  <entry>...</entry>                         <!-- one per result -->
</feed>
```

### Entry Elements

```xml
<entry>
  <id>http://arxiv.org/abs/{arxiv_id}</id>
  <title>Article Title</title>
  <published>2003-07-07T13:46:39-04:00</published>   <!-- version 1 date -->
  <updated>2003-07-07T13:46:39-04:00</updated>        <!-- retrieved version date -->
  <summary>Abstract text...</summary>

  <author><name>Author Name</name></author>           <!-- one per author -->
  <arxiv:affiliation>Institution</arxiv:affiliation>  <!-- if provided -->

  <!-- Links -->
  <link rel="alternate" type="text/html" href="...abs/..."/>   <!-- abstract page -->
  <link rel="related" title="pdf" href="...pdf/..."/>          <!-- PDF -->
  <link rel="related" title="doi" href="..."/>                 <!-- DOI (if present) -->

  <!-- Classification -->
  <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  <arxiv:primary_category term="cs.LG" scheme="..."/>

  <!-- Optional metadata -->
  <arxiv:comment>23 pages, 8 figures</arxiv:comment>
  <arxiv:journal_ref>Eur.Phys.J. C31 (2003) 17-29</arxiv:journal_ref>
  <arxiv:doi>10.xxxx/...</arxiv:doi>
</entry>
```

**Tip:** Extract the arXiv ID by stripping the `http://arxiv.org/abs/` prefix from `<id>`.

---

## Python Example (minimal)

```python
import urllib.request as libreq

url = (
    "http://export.arxiv.org/api/query"
    "?search_query=all:electron&start=0&max_results=5"
)
with libreq.urlopen(url) as response:
    data = response.read()
print(data.decode("utf-8"))
```

### With `feedparser` (recommended for parsing)

```python
import feedparser
import time

BASE_URL = "http://export.arxiv.org/api/query"

def search_arxiv(query, start=0, max_results=10):
    url = f"{BASE_URL}?search_query={query}&start={start}&max_results={max_results}"
    feed = feedparser.parse(url)
    return feed

feed = search_arxiv("ti:transformer+AND+cat:cs.LG", max_results=5)
print(f"Total results: {feed.feed.opensearch_totalresults}")

for entry in feed.entries:
    arxiv_id = entry.id.split("/abs/")[-1]
    print(f"\nID:      {arxiv_id}")
    print(f"Title:   {entry.title}")
    print(f"Authors: {', '.join(a.name for a in entry.authors)}")
    print(f"Published: {entry.published}")

# Paging example (always add delay between calls)
def fetch_all(query, page_size=100):
    results = []
    start = 0
    while True:
        feed = search_arxiv(query, start=start, max_results=page_size)
        results.extend(feed.entries)
        total = int(feed.feed.opensearch_totalresults)
        start += page_size
        if start >= total:
            break
        time.sleep(3)  # be polite
    return results
```

---

## Error Handling

Errors are returned as Atom feeds with a single `<entry>` where:
- `<title>` = `"Error"`
- `<summary>` = human-readable error message

Common errors:

| Cause                          | Example query                                        |
|--------------------------------|------------------------------------------------------|
| `start` not an int             | `?start=not_an_int`                                  |
| `start` < 0                    | `?start=-1`                                          |
| `max_results` not an int       | `?max_results=not_an_int`                            |
| `max_results` > 30000          | `?max_results=30001`                                 |
| Malformed arXiv ID             | `?id_list=1234.1234` (wrong digit count)             |

---

## Subject Categories (examples)

| Category  | Field                          |
|-----------|--------------------------------|
| `cs.LG`   | Machine Learning               |
| `cs.AI`   | Artificial Intelligence        |
| `cs.PL`   | Programming Languages          |
| `cs.AR`   | Hardware Architecture          |
| `hep-ex`  | High Energy Physics—Experiment |
| `quant-ph`| Quantum Physics                |
| `math.CO` | Combinatorics                  |

Full taxonomy: https://arxiv.org/category_taxonomy

---

## Article Versioning

```bash
# Latest version
http://export.arxiv.org/api/query?id_list=2301.00001

# Specific version (v2)
http://export.arxiv.org/api/query?id_list=2301.00001v2
```

- `<published>` = date version 1 was submitted
- `<updated>` = date the *retrieved* version was submitted
- If version 1, `published == updated`

---

## Rate Limiting & Caching

- Results update **once per day** (midnight); do not poll more frequently
- Add a **3-second delay** between consecutive API calls in scripts
- Use `<opensearch:totalResults>` to determine total pages before paging
- For bulk harvesting (>30k records), use the **OAI-PMH** interface instead:  
  https://info.arxiv.org/help/oa/index.html