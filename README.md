# Atlas investigation workbench

A working, single-user local application based on the observed investigation workflow. Cases, evidence, graph links, jobs, and report versions persist in SQLite. No third-party Python or JavaScript packages are required.

## Start

Run **Start-Atlas.ps1** with PowerShell. It starts a hidden local server and opens `http://127.0.0.1:8765`. It uses the bundled Python on this computer, or Python from PATH. Python 3.11+ is required.

Use **Restart-Atlas.ps1** to replace the running preview with a fresh process, including after configuring provider credentials. The updated preview completed a real standalone RDAP lookup from the browser. Successful connectivity still depends on your machine's firewall and provider access. Startup prevents duplicate servers from binding the same port.

From a terminal, the equivalent is:

```powershell
python app.py
```

The data directory defaults to `data/` next to the application. An alternate location can be supplied with `--data PATH`. An alternate port can be supplied with `--port 8766` (or `-Port 8766` to the launcher). Use **Stop-Atlas.ps1** to stop a server started by the launcher. Stop active collection through the app first so in-flight provider responses can finish.

## First-time setup

1. Start Atlas, open **Setup**, and choose **Enter / update API keys**.
2. Enter your provider keys. Leave **Remember with Windows encryption** checked to load them automatically at the next startup. Changes activate immediately when no collection job is active.
3. Run a standalone lookup or create a case and use **Hermes → Prepare plan** to review a bounded investigation before starting it.
4. Read complete evidence, apply selected leads, compare responses, and generate a report. Use **Setup → Download workspace backup** to preserve all case history.

This is a working local app, not verified feature-for-feature WebVetted parity. Read [FEATURE-PARITY.md](FEATURE-PARITY.md) for the captured workflow coverage, provider gaps and publicly advertised capabilities that remain unverified. [HERMES.md](HERMES.md) documents the prepared agent interface; connecting the user's existing Hermes deployment is deferred.

## Working features

- Multiple editable cases and typed seed entities; entity editing, related entities, manual source evidence and links. Reversible Trash for cases, nodes, edges, answers and monitors preserves source evidence.
- Interactive graph with pan, zoom, node dragging, saved positions and viewport, layout reset, search, type filters, an entity inspector, and evidence backlinks.
- Evidence vault with complete returned field values expanded by default, source records, timestamps, SHA-256 hashes, conservative extraction, selective application, and review notes/statuses.
- Evidence comparison with complete before/after values, added/removed/changed fields, same-source history, and a downloadable comparison JSON. Use **Evidence → Compare evidence**, or **Source history / compare** inside an evidence record. Arrays compare by position; changed ordering may appear as changes. Source/request differences are flagged, and both original records remain unchanged.
- Entity deduplication by type and normalized identifier for new extractions. Imported nodes and edges retain each original source record, even when identifiers repeat. Separate evidence links preserve multiple observations. Names are not automatically treated as verified common identity.
- Persistent collection jobs with limits of 1–30 connector runs, 0–2 expansion levels, cancellation, explicit retries, and an activity trail. Expansion is opt-in; automatic application does not imply verification.
- Internal collection, graph expansion, deeper expansion, web corroboration, and report generation. Unrequested or unreachable stages need not execute. Progress is based on actual outcomes, not invented credit percentages.
- Restart recovery marks in-flight work interrupted. It never automatically retries an uncertain charged request. Previously queued work resumes.
- Versioned reports containing complete stored evidence, graph records and collection outcomes, optional AI interpretation, printable HTML / browser PDF, and case JSON export. Older summary reports remain available and are labelled as legacy summaries.
- Search across every stored evidence field, with matching field paths and complete values in local answers. Optional AI answers validate evidence IDs; citation existence does not verify claim accuracy.
- Scheduled source refresh while the application is running. Response-hash changes are recorded in Activity. No email/push notification service is included.
- Monitor change alerts link to the exact saved response pair. **Compare last change** remains available after subsequent unchanged checks; **Latest evidence** opens the newest result.
- Import a full WebVetted investigation JSON, an evidence array, the captured graph HAR with response bodies, or an Atlas export. Imports create a new case and do not make live provider calls. HAR requests, headers, and cookies are never saved. Graph/evidence IDs are remapped. Original source IDs and timestamps are retained. Dangling graph edges are skipped and counted in Activity.

## Connector coverage and API setup

See [FREE-SOURCE-COMPARISON.md](FREE-SOURCE-COMPARISON.md) for the reviewed free/local alternatives, which paid features they could replace, code-quality findings, and the proposed implementation order. These candidates are not yet installed adapters.

**68 adapters are implemented.** They provide standalone phone, email, name/person, username, wallet, social-profile, domain, IP, location/business, and image-URL lookup workflows. 51 of the 73 captured transform IDs now have an adapter; 22 remain unimplemented. Some adapters use alternative providers and have narrower scope than the original feature. Catalog entries alone are not executable integrations.

Read **[API-SETUP.md](API-SETUP.md)** for provider links, the core shopping list, account requirements, visibility behavior, pagination, and every remaining gap. **[connector-coverage.json](connector-coverage.json)** lists each transform, exact coverage, credential setting names, and source documentation.

Use **Setup → Enter / update API keys** for immediate activation and optional Windows DPAPI persistence in `data/credentials.dpapi`. Blank inputs retain existing values. Uncheck persistence for session-only settings. Keys are not returned by the settings API, included in exports/backups, or passed to Hermes. Environment variables and the legacy **Connect-APIs.ps1** helper remain supported; that helper uses process-only settings. Availability means settings are present, not that paid account entitlement has been verified.

Standalone Lookup can create its own case or attach to an existing case. Full returned source bodies are retained with authentication-secret protection, full-response downloads, and explicitly bounded cursor pagination. Phone numbers, email addresses, names, and addresses are not content-masked. Provider-withheld fields remain unavailable. Optional image classifications and URL reputation annotations do not suppress results.

Running a connected provider is an actual network request and can incur charges under your account. The job limit counts connector runs, not dollars: DNS makes multiple requests and AI web search can use tools. Use your provider's account-side spending limits for monetary control. No paid calls are made just by opening Atlas or importing a capture. Configured monitors do make calls on their schedule.

AI report/answer actions send all eligible evidence records and their complete stored fields to the configured OpenAI API, with `store: false`. If the context exceeds `ATLAS_AI_MAX_CONTEXT_CHARS` (default 200,000 characters), the action stops before sending and reports the limit; it does not substitute excerpts. AI interpretation is an optional narrative and does not replace the full evidence in reports. Web corroboration sends the selected identifier to the web-search tool. Complete baseline reports and full-field search work without AI and are not subject to its context limit.

## Data, privacy, and operational limits

- This build listens only on `127.0.0.1`. It has local Host/Origin checks and a per-process write token, but **no multi-user login, roles, encrypted database, or production hosting setup**. Do not expose it through a public proxy. Hosting requires additional engineering.
- Known authentication/password fields and recognizable credential patterns are redacted. Only relevant response bodies are parsed from HARs. Redaction cannot certify an arbitrary document contains no secrets; inspect files before sharing exports.
- Source identifiers and research evidence can be sensitive. They are stored locally in plaintext SQLite and may be included in case exports. Manage backups and local machine access accordingly.
- URL fetches reject private/local destinations and credential-bearing URLs. Public websites and APIs may rate-limit, change shape, or deny access. Atlas does not bypass those restrictions.
- A hash proves consistency of the locally stored sanitized response, not source authenticity or forensic chain of custody. No screenshot capture or external timestamp/signature service is implemented.
- Review status is an analyst judgment. A “supported” label does not independently verify a source claim. Excluded evidence is omitted from new reports/AI contexts but retained in the vault.
- Monitor hash comparisons include provider metadata, so changed timestamps can generate change events. Checks run only while the server is running. A missed interval results in at most one new scheduled check, not a burst of backfilled requests.
- Report versions are immutable text snapshots; their evidence links open the current vault record. Original report text is retained when later reviews change.
- JSON exports contain all stored case record types. The importer restores graph, evidence, and historical run records as a new case; it does not restore active schedules, jobs, report versions, or question history. For a consistent full case backup, use **Setup → Download workspace backup** while Atlas runs. `Restore-Atlas.ps1 -Backup <zip> -Destination <new-folder>` restores all database history to a new folder and disables scheduled/unfinished requests. Start it using `Start-Atlas.ps1 -DataDirectory <new-folder> -Port 8766`. Credentials remain separate.
- No automatic person merging, identity scoring, source authenticity guarantees, or fake provider responses. The demo is explicitly fictional.
- Permanent deletion, automatic entity merging, local image upload/screenshot capture, the remaining provider adapters, and multi-user hosting are not implemented in this version. Reversible removal and restoration are implemented. Image lookup currently accepts public URLs. Cursor pagination is implemented where documented; per-source limits are visible.

## Investigation plans and Hermes

The **Hermes** tab offers a local, deterministic source planner. It records the objective, selected seeds, source choices, shared run budget, expansion settings, request options and coverage gaps before collection. A saved plan starts once; preparing it makes no external request. The objective is context for the analyst, not a claim that the planner reasons autonomously.

The optional MCP bridge exposes 21 tools for the existing Hermes agent to plan, collect, inspect, add research evidence, review, report and monitor. It uses the running Atlas API and does not write Hermes files or read provider keys. The user's separate BT/Hermes integration is left for later.

## Validation

Run:

```powershell
python -m unittest discover -s tests -v
```

Tests cover evidence/edge provenance, selective application, recursive limits, cancellation, failures, restart recovery, import remapping and rollback, exclusion/report versions, AI citation bounds, provider request contracts, secret redaction, and local HTTP write protection. See `VALIDATION.md` for the observed run results and remaining live-provider checks.

## Source documentation

- [OSINT Industries request API](https://docs.osint.industries/reference/search-1)
- [ScrapeCreators Instagram profile](https://docs.scrapecreators.com/v1/instagram/profile/)
- [ScrapeCreators Instagram posts](https://docs.scrapecreators.com/v2/instagram/user/posts/)
- [GitHub public user API](https://docs.github.com/en/rest/users/users#get-a-user)
- [Google public DNS JSON API](https://developers.google.com/speed/public-dns/docs/doh/json)
- [RDAP bootstrap service](https://about.rdap.org/)
- [OpenAI Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)

The adjacent analysis deliverables distinguish directly captured Varda behavior from inference. `catalog.json` is captured reference metadata; proprietary class-name strings are never executed.
