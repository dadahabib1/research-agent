# Searching, fetching and recording sources

How a run finds evidence and records the search. The researcher subagent carries a summary of this file in its own definition; the main session uses it to plan (step 4) and to write the delegation prompt. The owning sources of a field (its endpoints, registries and data files) are listed in the project's domain rules, heading 6, not here.

## 1. Owning source first

Before any search, name the source that owns the fact and go to it: the regulator's filing API, the statistics agency's data file with its vintage parameter, the standard-setter's document store, the registry that holds the abstract, the package index's metadata, the library's source at the pinned version. In the first plugin run, every decision-critical number that held up came from such an endpoint; every search-only chain ended in a secondary summary or a blocked page.

## 2. Query shape

- Three to seven words that name a document, an identifier, a standard, or an author and year reach primary sources: "<standard-setter> <standard number> effective date", "<author> <author> <year>".
- Concept phrasing ("industry leading indicators peer-reviewed") returned blogs or nothing. Quoted titles and adding "pdf" led to blocked hosts, not open ones.
- Vary phrasing between attempts and never repeat a query verbatim. Shorter is better. Run independent searches in parallel.
- When recency matters, pair a general query with a dated or year-bounded one.

## 3. Open what you cite

A search snippet is not a source. Fetch the page and read the part that supports the claim. Record how the page was fetched:

| Fetch | What the researcher saw | Rule |
|---|---|---|
| Raw | The page text itself: the plugin's `fetch_raw` tool, a data file, an API response | Label raw-fetched; cite normally |
| Summary | A fetch tool's paraphrase of the page (Claude Code's WebFetch answers a prompt about the page with a smaller model and truncates) | For discovery and orientation only. A value taken this way is labelled summary-fetched (`standards.md`) until `fetch_raw` or a second route confirms it |
| Snippet | Search-result text only; the page did not open | Label snippet; keep it off decision-critical paths |

Every decision-critical number, date, quotation or rule text comes from `fetch_raw` (raw-fetched) or from a second route that confirms it. `fetch_raw` returns a header (status, final URL, content type, fetch time, sha256 of the body, route) and then the text: HTML as markdown with every table cell kept, superscripts as `^[x]` and subscripts as `_[x]`, PDFs per page. Long documents come in pages: call again with the `next_offset` it returns until it is `none`. Firecrawl's own markdown, parse and JSON outputs are not raw: they merge superscripts into numbers, escape characters or come from a model, so their values are summary-fetched too.

The incident behind the rule: a summary of an exchange calendar invented an early-close date that the page's footnotes did not contain, and the run caught it only by reading the raw page (`takeaways.md`, entry 36).

## 4. When a page will not open

A 403 or 503, a redirect to an unblock page, a PDF with no text layer, a page that renders only with JavaScript:
- try the publisher's own storage or document host (standard-setters often serve PDFs from a separate domain), a regional mirror, or the abstract's registry;
- for a paywalled book, cite the chapter from the publisher's table of contents or index;
- `fetch_raw` with its default route already retries a blocked page through Firecrawl when the project has set `FIRECRAWL_API_KEY`; it does not run JavaScript itself;
- a `fetch_raw` result with status BLOCKED (a bot wall, captcha, login or JavaScript-only page) or ERROR has no content: it is a dead end to log, never content;
- otherwise record the attempt under Dead ends with the status and reason, label any dependent claim snippet, and never save an error body as a document (entry 38).

## 5. Lateral reading

Before relying on a source, leave it: investigate who publishes it and why; find better coverage of the same claim from sources already trusted; trace the claim, quotation or figure to its original context. These moves, with "stop" before them, are Caulfield's SIFT, and they are the protocol's "trace every claim to the source that owns it" in practice.

## 6. Citation chasing and a documented search

Systematic-review practice adds two habits: follow the reference lists of the sources you use, and the later work that cites them; and record every search so that it can be re-run (engine or database, query, date, results). The log's Searches table, with its Tool column, is that record; the Sources table, with "used or rejected, and why", is the selection record.

## 7. Measure instead of search

When the claim is about the project's own data or system, do not search for someone else's number: write the script, name the sample, report the interval. A measurement is its own evidence kind (`standards.md`).

## 8. Latest edition

For every recurring source (annual scorecards, data releases, methodology documents, package versions), search for a newer edition before citing the one in hand, and record the check in the Sources table. A newer edition that will not open is a Dead end and a caveat on the claim.

## 9. When to stop

Stop a question when it has cited evidence or an explicit gap, when two further searches add nothing new, or at about fifteen tool calls. Report "no reliable source found" as a result.

## Sources

Paraphrased; no text copied. "Opened" means the page itself was read, in full or in the relevant part.

| Source | URL | Licence | Status | Used for |
|---|---|---|---|---|
| Research log and notes of the first plugin run (system review v1, 2026-10-05), in the consuming project's repository | private repository | the project's | Opened | Query shapes that worked and failed; blocked hosts; the summariser incident; the owning-endpoint pattern |
| Anthropic, deep-research skill, `references/researcher.md` (claude.ai skill, 2026) | distributed with Claude; no public URL | Anthropic's; not open | Opened (local copy) | Short queries; never repeat a query; fetch full pages because snippets lose context; parallel calls; stop conditions |
| Everything Claude Code (ECC) plugin 2.2.3, `skills/deep-research/SKILL.md` and `skills/exa-search/SKILL.md` | https://github.com/affaan-m/ECC | MIT (Affaan Mustafa, 2026) | Opened (local copy) | Keyword variants per sub-question; mixing general and dated queries; search operators |
| Cochrane Handbook for Systematic Reviews of Interventions, version 6.5.1 (March 2025), chapter 4 "Searching for and selecting studies" | https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04 | Copyright Cochrane; all rights reserved | Opened (first part of the chapter) | Several sources, not one; documented and peer-reviewed search strategies; re-running searches before publication; checking reference lists; grey literature; reporting restrictions |
| Rethlefsen et al., "PRISMA-S: an extension to the PRISMA Statement for Reporting Literature Searches in Systematic Reviews", Systematic Reviews 10, 39 (2021) | https://doi.org/10.1186/s13643-020-01542-z | Open access; licence not confirmed (full text behind a cookie gate and a CAPTCHA when checked) | Abstract (PubMed 33499930) and the PRISMA site's summary page opened; full text not opened | A search report complete enough to be reproduced: 16 items covering sources, strategies, dates and results |
| Mike Caulfield, "SIFT (The Four Moves)", 19 June 2019 | https://hapgood.us/2019/06/19/sift-the-four-moves/ | CC BY 4.0 | Opened | Stop; investigate the source; find better coverage; trace claims to the original |
| Firecrawl, scrape endpoint documentation | https://docs.firecrawl.dev/features/scrape | Firecrawl's | Opened | What a raw-fetch tool returns: the page as markdown, PDF parsing, JavaScript rendering, cache age |
| Mikhail Shilkov, "Inside Claude Code's Web Tools: WebFetch vs WebSearch", October 2025 | https://mikhail.io/2025/10/claude-code-web-tools/ | the author's | Opened | How WebFetch summarises a page with a smaller model and truncates |
