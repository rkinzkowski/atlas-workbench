# Validation record — updated 2026-09-19

## Automated checks

**68 tests passed** with the bundled Python runtime. JavaScript syntax checking passed. All five PowerShell launch/setup/restore scripts parsed without errors.

The suite covers source-preserving imports, duplicate identifiers, entity/edge provenance, cross-case validation, failed-import rollback, source availability, credential redaction, private network blocking including DNS rebinding, null MX handling, collection budgets, recursive expansion, cancellation after an in-flight request, no automatic application by default, explicit retry/restart behavior, monitor changes and pause controls, report immutability/exclusions, AI evidence-ID bounds, provider request fixtures, phase order, and local HTTP write protection.

## Actual supplied HAR

Imported the final full investigation response from the supplied graph HAR into a local case, without making source lookups. Result:

| Record type | Imported |
|---|---:|
| Nodes | 479 |
| Edges | 629 |
| Evidence | 47 |
| Historical transform runs | 36 |
| New collection jobs | 0 |

All edge endpoints and evidence references resolve. Original node IDs are preserved as source identifiers. Duplicate identifiers remain separate imported source records. Every imported evidence item starts unreviewed. No HAR request headers, cookies, or authorization material were persisted.

## Real network checks

Public test inputs were `example.com` and GitHub's public `octocat` profile. No personal case identifiers or provider credentials were sent.

| Adapter | Observed outcome |
|---|---|
| RDAP registration | Successful real response |
| Website contacts/links | Successful real response |
| Google public DNS | Successful real responses |
| GitHub public profile | HTTP 403; no successful live validation in this environment |

A complete backend job using the three successful public adapters finished with **3 completed, 0 failed**, captured three evidence items, and saved a versioned report.

**Earlier preview limitation, now resolved for the tested path:** older browser-triggered calls encountered Windows socket error 10013, while approved direct checks succeeded. A later browser check found duplicate preview processes serving different code versions. Those Atlas processes were replaced with one current instance, and exclusive port binding was added. The current preview successfully completed a browser-triggered standalone RDAP lookup for `example.com`: one completed source, zero failures, evidence E52, and a saved report in case 4. This validates that path; it does not establish that every provider is reachable or that duplicate processes caused the earlier socket failures. The old failed attempts remain visible as historical failures.

## Browser checks

Verified rendered screens and these interactions in the local app:

- Open the fictional demo and inspect its graph and entity panel.
- Inspect evidence review controls, extracted entities, and the source-response/hash disclosure.
- Create a new public test case from a typed domain seed.
- Choose public sources and queue a bounded collection job.
- See blocked attempts recorded as failed, without fabricated evidence.
- See the independently executed successful backend job's real evidence appear in the vault.
- Apply two extracted nameserver leads and observe the graph grow to three nodes and two evidence-linked edges.
- Search case evidence and receive a valid, clickable evidence citation.
- Inspect saved report versions and disabled AI controls when credentials are absent.

The final full-response download link emitted a confirmed browser download event. The source-response HTTP endpoint was separately tested for JSON field preservation, authentication-secret redaction, and an attachment header. The browser print dialog, long-duration scheduling, all possible input formats, and paid-provider responses were not exhaustively exercised. Report HTML and export endpoints are implemented; production hosting, multi-user security, and full catalog parity are outside this build.

## Expanded standalone lookup validation

- Phone and email source lists switch correctly and show specific missing credential settings.
- A standalone domain lookup created its own persistent case, saved actual RDAP evidence, and generated a report.
- Offline fixtures exercise standalone phone, email, name, and username jobs and verify full returned fields remain available.
- All 31 ScrapeCreators route/input definitions match a snapshot derived from the official OpenAPI document. Ten cursor adapters use documented response cursor fields.
- Cursor tests cover collection limits, continuation, repeated cursors, cancellation before requesting, and retention of prior pages after a later failure.
- Provider tests cover OSINT Industries types and premium switches, People Data Labs matching context, no-match 404 versus access failures, specialist routes, TinEye page offsets, Serper page/scope options, and full unknown-field retention.
- Tests verify phone/email/name/address values and pagination tokens are not masked, authentication data is redacted, and more than 1,200 extracted leads survive the former limits.
- Server exclusivity prevents two instances from binding the same port. The port is acquired before restart recovery modifies persisted jobs.

## Paid and unimplemented coverage

**68 adapter implementations** are present: 63 require account settings and five use public endpoints. **51 of the 73 captured IDs have an adapter; 22 remain unimplemented.** Several mapped IDs use alternative providers or narrower functionality, so this is not complete provider parity. `connector-coverage.json` and `API-SETUP.md` identify exact coverage, account requirements, and remaining gaps.

Paid adapters were initially checked using primary documentation and synthetic offline fixtures. Live access, purchased field bundles, rates, per-provider pagination completeness, and successful extraction still require account testing. The secret-entry helper was syntax-checked but not exercised with real credentials; keys for the following self-test were configured separately through the app.

### Authorized two-request self-test — September 19

The user supplied their own Instagram identifier. One ScrapeCreators profile request returned HTTP 200 with `success: true`, but also `error: not_found`, `errorStatus: 404`, and `message: Profile is private`; the response reported one charged credit. No profile data was returned. One Serper exact-handle query returned HTTP 400 with `Query pattern not allowed for free accounts.` These observations do not establish that every private profile or every free-tier query behaves the same way.

The first response exposed an incorrect success classification. The adapter now treats a nonempty top-level error, a failing errorStatus, or success=false as a provider failure, retaining the full sanitized error response. Three offline regression tests verify this contradictory envelope, partial pagination, and job-level failure accounting without retries. Existing test records were corrected with an audit event; the original response/hash and earlier immutable report remain, alongside a corrected report. Both keys survived reload. No additional provider requests were made. Neither connector has yet returned a successful live investigation result in this self-test.

The user then supplied another Instagram handle and explicitly requested a lookup. One additional ScrapeCreators profile request succeeded, charged one credit, and returned public profile fields plus twelve embedded post records. Atlas retained the complete response, extracted fourteen leads, generated a local report, and left graph expansion off. This validates one successful live Instagram profile retrieval; Serper remains unvalidated for successful results. The embedded timeline also reported `has_next_page: true` despite its count matching the twelve returned records, so completeness beyond this response is not assumed. No continuation was requested.


## Complete detail visibility

Six additional automated tests verify complete report values, fields beyond former excerpt lengths, searches across 36 records, complete AI context or an explicit stop before requesting, analyst exclusions, long notes, all extracted leads, and on-demand report loading. Synthetic name, phone, email, address, and unknown fields survive while authentication secrets remain protected.

Browser verification on September 19 used the existing public `example.com` RDAP evidence, without another source lookup or any paid request:

- Opening E52 displayed all 81 returned leaf values in the expanded field table.
- Searching `delegationSigned`, a raw response field absent from the summary, found E52.
- Generating report version 2 produced complete records, including that raw field, graph records, and collection outcomes. Its rendered text contained 7,322 characters.
- Version 1 remained available and labelled as a legacy summary. No browser console errors were observed during this check.

Paid provider response completeness and account entitlements remain unverified. These checks establish retention and display of returned data, not recovery of fields a provider does not supply.

## Evidence comparison and monitor history

Six additional automated tests cover complete nested before/after values, absent versus null fields, exact JSON types, arrays by position, empty roots, unchanged key ordering, case boundaries, differing request settings, authentication-secret protection, old monitor hash recovery, retention of the exact changed pair after later unchanged checks, and HTTP comparison downloads.

Browser checks used a separate temporary database with two synthetic source responses and a paused monitor. The evidence selector suggested the prior response from the same entity and transform. The comparison displayed one added, one removed, and one changed field, including complete before/after values and explicit missing-field labels. The monitor's **Compare last change** opened that same pair. The layout was visually inspected; no console errors were observed. No real case data was added or modified and no provider requests were made during these checks.

Comparisons cover stored source responses. They do not infer real-world deletion from an absent field or match array items by identity. Different sources, request options, pagination coverage, and provider timestamps can account for differences; source metadata and full responses remain available for review.

## Plug-and-play workflow release

Thirteen additional automated tests cover no-call planning, start-once plans, source/case validation, expansion source types, retained provenance during edits/removal/restoration, monitor pause behavior, layout reset, active-job protection, setting allowlists and secret non-disclosure, real Windows DPAPI save/load/removal, a subprocess MCP handshake and full-evidence tool call, malformed MCP messages, complete database backup/restore, integrity rejection, no replay of restored jobs, agent answer citations, and explicit monitor state changes.

The synthetic browser preview verified Setup readiness, the key-entry form and encrypted-persistence option, a three-source plan preview without execution, editing a case, moving it to Trash, and restoring it. No browser console errors were observed. Browser testing used an isolated temporary database; it did not mutate the user's imported investigation or query providers.

The user's Hermes handoff was reviewed as architecture context. No Hermes host/profile/agent files were changed. The local bridge is tested, but deployed Hermes interoperability is deferred by user request. Paid account verification and personal-data accuracy checks remain pending the user's keys and selected test identifiers.
