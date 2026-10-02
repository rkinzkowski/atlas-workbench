# Free-source alternatives for Atlas

Reviewed 2026-09-19. This is a source-code/documentation comparison and implementation recommendation, not a live benchmark or a list of newly installed integrations. No third-party tools were executed, account sessions retrieved, or paid lookups made for this review. Atlas's existing provider adapters remain unchanged.

## Existing baseline

Inspected `providers.py`, `connectors.py`, and the coverage register. Atlas has 68 implemented adapters. ScrapeCreators provides 31 social adapters; Serper provides nine web/places adapters. Other implementations include OSINT Industries, PDL, Twilio, HIBP, IPinfo, and specialist services. Implemented does not mean configured or validated. The user's ScrapeCreators profile lookup succeeded on one public Instagram account; a private-profile request failed, and the Serper exact-handle request was rejected by the free account.

Atlas already has no-key DNS, RDAP, single-page website collection, GitHub public profile, and memory.lol adapters. Basic local phone-number intelligence and broad direct username discovery are genuine gaps.

## Comparison

| Supplied project | Atlas overlap | What can avoid provider charges | Boundary and recommendation |
|---|---|---|---|
| [Blackbird](https://github.com/antoniaci/blackbird) | `username_web_search`, parts of `username_osint_industries`; email presence is adjacent | Direct site checks can find candidate username accounts without a search-provider key. The project advertises a 600+ site list, not 600 independently verified current successes. | Highest-priority discovery candidate. Finding a profile URL does not replace ScrapeCreators post/profile enrichment or Serper's whole-web index. Audit email checks individually before enabling them. |
| [Toutatis](https://github.com/megadose/toutatis) | `instagram_profile` | Direct Instagram profile requests may avoid ScrapeCreators credits when they succeed. | Requires an Instagram session. Source has profile retrieval plus a separate obfuscated-contact lookup called by its CLI. Prefer a profile-only integration first; no guarantee of private content, complete contacts, or live reliability. |
| [007-TheBond](https://github.com/Deadshot0x7/007-TheBond) | Instagram, phone metadata, username/web search, IP, email validation/breaches | Its local phone library is useful; its direct Instagram and basic IP approaches offer candidates for cheaper collection. | Select individual approaches. Do not import the whole tool as equivalent coverage: email-breach logic is incorrect, username detection is weak, and Instagram output drops fields. Details below. |
| [GHunt](https://github.com/mxrch/GHunt) | Part of `email_osint_industries`; adjacent to the unimplemented Google account transform | Local Google-specific email/Gaia/Drive investigation can reduce dependence on a paid aggregator for that subset. | Python 3.10+, authenticated Google setup and JSON export are documented. It does not replace broad email-to-social or PDL person enrichment. Candidate after username discovery; user completes login locally. |
| [DetectDee](https://github.com/Yvesssn/DetectDee) | Username discovery; portions of email/phone presence | Direct template-driven site checks; optional AI is not required for core detection. | Secondary candidate to compare against Blackbird for unique working sites. README points installation at `piaolin/DetectDee`; resolve exact upstream/version first. Phone/email support does not establish person identity or guarantee a full reverse lookup. |
| [PhoneInfoga](https://github.com/sundowndev/phoneinfoga) | `phone_line_lookup`, `phone_web_search` | Local parsing/formatting and search-link generation can be free of provider fees. | Upstream labels the project unmaintained. External scanners still have their own accounts/limits. Prefer a small local phone adapter; retain Twilio for separately requested network intelligence/caller-name fields. |
| [email2phonenumber](https://github.com/martinvigo/email2phonenumber) | Superficially overlaps email/phone enrichment | No dependable equivalent replacement established. | Author calls it a proof of concept and says supported services introduced protections. It uses account-recovery weaknesses and candidate enumeration, not a general person-data source. Defer as an automated Atlas integration. |
| [All-Dorks-in-one-place](https://github.com/RhackrExplorer/All-Dorks-in-one-place/tree/main) | Serper search transforms | Public-profile/domain/document search templates and manually opened search links do not require a search API. | A query library, not a search backend. Automated Serper execution remains billed/restricted. Curate relevant public-information templates; do not bulk-import password/credential discovery entries, consistent with the user's original secret-exclusion request. |
| [phone2email](https://github.com/whitef0x0/phone2email) | No equivalent person-email discovery | Generates SMS gateway addresses for US/Canadian numbers. | Not an owner's personal email address. The implementation uses Twilio carrier lookup, so it is not independent of a provider account. Low value for Atlas's present investigation scope. |
| [Scrapy](https://www.scrapy.org/) | Extends `domain_contacts`; could support custom public-page collectors | Self-hosted fetching, parsing, throttling, and JSON export. | A crawler framework, not a ready-made replacement for 31 social APIs. Each site needs maintained extraction logic; browser rendering is an extension. Valuable for bounded website crawls. |
| [OSINT Handbook](https://www.osinthandbook.com/terms) | Source discovery and investigation planning | Helps find additional public sources. | A resource directory, not a lookup API. Homepage content was not extractable in this review; its own terms confirm the directory role. Preserve links/attribution rather than copying the catalog wholesale. |

## Code findings that affect equivalence

**007-TheBond email breach check:** [EmailLookup.py](https://github.com/Deadshot0x7/007-TheBond/blob/master/scripts/EmailLookup.py) hashes the input email and calls the Pwned Passwords range endpoint, then labels the result as email compromise. [HIBP's documentation](https://haveibeenpwned.com/API/v3) distinguishes password hashes from authenticated email-account breach searches. The former cannot answer the latter. Keep Atlas's actual `breachedaccount` adapter.

**007-TheBond username checks:** [SearchUsername.py](https://github.com/Deadshot0x7/007-TheBond/blob/master/scripts/SearchUsername.py) treats HTTP 200 as a match. A generic page or redirected login can satisfy that test. Atlas should require site-specific evidence and retain ambiguous/blocked outcomes.

**007-TheBond Instagram:** [Instagram.py](https://github.com/Deadshot0x7/007-TheBond/blob/master/scripts/Instagram.py) fetches profile JSON but only prints mapped fields. An Atlas adapter should retain the complete response; wrapping its console output would discard evidence that Atlas already preserves.

**Phone metadata:** The [007 phone module](https://github.com/Deadshot0x7/007-TheBond/blob/master/scripts/PhoneLookup.py) uses `phonenumbers` locally. The [library documentation](https://github.com/daviddrysdale/python-phonenumbers) describes number-plan validity, region/time-zone information and, where available, original carrier allocation. These are not proof that a number is active or of its current owner/carrier. [PhoneInfoga's scanner documentation](https://sundowndev.github.io/phoneinfoga/getting-started/scanners/) separates local parsing from external API scanners and generated search links. This review does not rely on its older pricing examples.

**IP lookup:** [007's IP module](https://github.com/Deadshot0x7/007-TheBond/blob/master/scripts/IpLookup.py) calls ip-api over HTTP. The [service's documentation](https://ip-api.com/docs/api:json) specifies no HTTPS on that free endpoint, a 45 requests/minute limit, and noncommercial use. It is narrower than replacing every IPinfo or AbuseIPDB field and should not silently become Atlas's default.

**Blackbird export:** The [CLI](https://github.com/antoniaci/blackbird/blob/main/blackbird.py) supports JSON, concurrency/timeouts and disabling automatic list updates. Its [email collector](https://github.com/antoniaci/blackbird/blob/main/src/modules/core/email.py) separates found/not-found/error internally but filters to found accounts before export. An Atlas runner must preserve all outcomes, distinguish a missing export from a successful empty result, and record the tested site list. No automatic identity merge follows a username hit.

**Toutatis:** [core.py](https://github.com/megadose/toutatis/blob/master/toutatis/core.py) confirms that its normal command also invokes the obfuscated-contact lookup. Profile retrieval and that additional action should not be silently bundled in Atlas. Source-masked values remain explicitly source-masked; missing characters must not be invented.

## Recommended implementation order — not yet implemented

1. Local phone parsing/metadata and email syntax/domain checks. No API fee; label exactly what those checks establish.
2. Blackbird-style username discovery with a bounded, versioned site set. Compare overlap and unique results against DetectDee before adding redundant requests.
3. Direct Instagram public-profile collection, compared field-by-field against the saved successful ScrapeCreators result. Keep ScrapeCreators as an explicitly selected fallback while direct reliability is unknown.
4. GHunt Google-specific evidence using a locally configured session and complete JSON records.
5. Bounded Scrapy public-site crawls and a curated public-information query library.

Atlas should offer a visible “free sources first” plan after these adapters pass validation. A blocked free request must remain visible. Paid fallback should use the user's selected providers and budget, and adding a connector must not silently enlarge recurring monitors. Retain returned details and content categories, show source/version/request count and limits, and keep secrets out of evidence/Hermes. Existing live APIs remain available for data that the local route does not provide.

## Validation needed before a switch

Use an authorized known-present account and a synthetic known-absent control, plus offline timeout/rate-limit/login-wall fixtures. Compare exact fields, omissions, false positives, request counts and duration. Confirm cancellation and no automatic paid retry. A direct Instagram trial can use the already authorized public test profile, with a bounded request count, without rerunning the paid baseline. No reliability or cost-savings percentage is claimed until measured.

None of these sources has demonstrated an equivalent replacement for PDL person records, every OSINT Industries module, historical DNS datasets, or Atlas's reverse-image providers. Keep those coverage gaps explicit. Version and license review remains part of packaging any actual third-party integration; no third-party code was bundled by this comparison.
