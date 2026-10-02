# Atlas API setup

Start with the four services below. They cover standalone phone, email, name and username searches, social profiles/posts, web search, and person enrichment. You do not need every optional service to use Atlas.

## Core services to gather

| Service | What Atlas implements | Local setting | Account detail |
|---|---|---|---|
| [OSINT Industries](https://docs.osint.industries/reference/search-1) | Email, phone, username, name, and wallet lookups | `OSINT_INDUSTRIES_API_KEY` | Search API access. Premium modules are an explicit lookup option; additional provider charges can apply. |
| [ScrapeCreators](https://docs.scrapecreators.com) | 31 profile, post, video, search, and profile-link-page connectors | `SCRAPECREATORS_API_KEY` | API credits and access to the selected endpoints. Pagination consumes additional requests. |
| [Serper](https://serper.dev) | Name, phone, email, username web searches; indexed LinkedIn/Facebook searches; business places | `SERPER_API_KEY` | Search API credits. Serper and SerpApi are different services. |
| [People Data Labs](https://docs.peopledatalabs.com/docs/reference-person-enrichment-api) | Person enrichment from name with context, email, phone, or LinkedIn profile | `PDL_API_KEY` | Choose access to the fields you need. The [free plan can return contact-field presence instead of actual values](https://docs.peopledatalabs.com/docs/fields). A name also needs location, company, or similar context. |

## Optional specialist services

| Service | Added capability | Local setting |
|---|---|---|
| [Twilio Lookup](https://www.twilio.com/docs/lookup/quickstart) | Phone validity, carrier/line type; optional caller name where available | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| [Have I Been Pwned](https://haveibeenpwned.com/API/v3) | Email breach exposure metadata; no leaked passwords | `HIBP_API_KEY` |
| [BuiltWith](https://api.builtwith.com/domain-api) | Website technologies and related returned domain metadata | `BUILTWITH_API_KEY` |
| [SecurityTrails](https://docs.securitytrails.com/docs/overview) | Known subdomains and domains associated with an IPv4 address | `SECURITYTRAILS_API_KEY` |
| [IPinfo Core](https://ipinfo.io/developers/core-api) | IP network and approximate geographic data | `IPINFO_TOKEN` with Core endpoint access |
| [AbuseIPDB](https://docs.abuseipdb.com) | IP abuse reports and source reputation scores | `ABUSEIPDB_API_KEY` |
| [SerpApi](https://serpapi.com/google-lens-api) | Google Lens and [Yandex reverse-image search](https://serpapi.com/yandex-reverse-image-api) | `SERPAPI_API_KEY` |
| [TinEye](https://github.com/TinEye/pytineye) | Reverse-image matches and source backlinks | `TINEYE_API_KEY` |
| [Sightengine](https://sightengine.com/docs/getstarted) | Image properties/type and optional content-label annotations | `SIGHTENGINE_API_USER`, `SIGHTENGINE_API_SECRET` |
| [Google Web Risk](https://docs.cloud.google.com/web-risk/docs/lookup-api) | URL threat-list matches | `GOOGLE_WEBRISK_API_KEY`; enable Web Risk in the associated Google Cloud project |
| [OpenAI](https://developers.openai.com/api/reference/resources/responses/methods/create) | Optional web corroboration, AI reports and evidence questions | `OPENAI_API_KEY`, `OPENAI_MODEL` available to your account |

No paid keys are needed for public DNS, RDAP, one-page website contact/link extraction, GitHub public profiles, or the [public memory.lol username-history endpoint](https://github.com/travisbrown/memory.lol). Rate limits and source restrictions still apply. memory.lol limits unauthenticated history; Atlas does not claim full-history access.

## Connect the keys locally

1. Open **Setup → Enter / update API keys** in Atlas. Stop active collection before changing keys.
2. Enter the provider values and select **Remember with Windows encryption** to persist them for your Windows user. Blank fields retain existing settings; explicit removal clears a setting.
3. Save. Connected sources update immediately without restarting or making a paid test request.
4. Open **Lookup**, choose the identifier type and sources, then run. Alternatively, create seeds in a case and use **Hermes → Prepare plan** to review collection and expansion before starting.

Windows stores saved keys in `data/credentials.dpapi`, encrypted through DPAPI for the current OS user. Session-only settings expire with the process. Environment variables remain supported on every platform. The legacy **Connect-APIs.ps1** helper enters process-only settings and restarts Atlas; it does not save those values. Keys entered through the UI are never returned to the browser, included in case exports or workspace backups, or exposed by Hermes tools.

The Sources screen checks whether required settings exist. It cannot verify account access without making a real request. Selecting a connected source makes a real provider request and may incur charges. Opening Atlas or importing a capture makes no paid calls. Never paste credentials into case notes or chat.

In the September 19 self-test, Serper rejected Atlas's quoted exact-handle query with `Query pattern not allowed for free accounts.` A configured free key therefore does not guarantee access to these search patterns. Atlas preserves the failure and does not silently broaden or retry the query. ScrapeCreators returned a private-profile error and charged one credit; a charge does not establish successful retrieval. See VALIDATION.md for the observed outcomes.

## Result visibility

Atlas retains successfully received source bodies without masking names, phone numbers, email addresses, addresses, or other content categories. Unrecognized fields remain in the full response and JSON download. Authentication secrets are redacted. API keys and your WebVetted session are never recovered from captures.

Provider-withheld, provider-masked, unavailable, deleted, or unreturned fields cannot be reconstructed. A provider's subscription bundle and response schema determine what it supplies. A successful response does not establish that an account belongs to the searched person.

Relevance searches and graph filters change a view; they do not remove stored evidence. Applying leads and excluding evidence from a report are explicit analyst actions. Image content labels and URL reputation annotations never suppress results.

Collection limits are visible: 1–20 pages per cursor-capable connector run, at most 30 connector runs per job, and a configurable 25 MB response-body ceiling (`ATLAS_MAX_RESPONSE_BYTES`). A response above that ceiling fails explicitly instead of being silently truncated. Provider error-body capture is separately limited to 100 KB and marked if truncated. All extracted leads are retained without a summary-count cap.

Ten ScrapeCreators adapters follow documented cursors. Use **Retrieve more pages** on evidence that contains a cursor. Each continuation creates a separate evidence record, preserving the earlier collection. A later-page error retains earlier successful pages and marks the run partial. Repeated cursors stop collection. Search-page selection applies to Serper, LinkedIn company posts, SecurityTrails reverse-domain lists, and TinEye (100 matches per page); it is independent of automatic cursor pagination. Other adapters retain one complete returned API payload, which is not a claim that the entire provider dataset was collected.


Opening an evidence record displays all returned field paths and complete values by default. The original JSON structure, extracted leads, collection notes, and stored metadata remain available. Evidence search examines every stored field; local answers return matching paths and values without the former result or excerpt caps.

New reports include complete stored evidence, graph records, and collection outcomes. Explicit analyst exclusions are listed, and excluded records remain searchable in the vault and available in exports. Older report versions remain immutable and are labelled as legacy summaries.

Optional AI interpretation receives complete eligible evidence or stops before sending when it exceeds `ATLAS_AI_MAX_CONTEXT_CHARS` (default 200,000 characters). It never silently substitutes excerpts. Baseline complete reports and local search work without AI and are unaffected by that input limit.

## Remaining vendor-specific gaps

Do not purchase an arbitrary Truecaller, Eyecon, CallApp, TruePeople/skip-trace, or WhatsApp reseller just because the name resembles the captured transform. We need the actual service documentation and your access to it. The capture contains internal class labels, not working credentials or complete third-party contracts.

OSINT Industries and People Data Labs can cover related use cases, but their results are labelled as their own data. They are not presented as replicas of the original private services. Paid adapters have offline request-fixture checks; account entitlements, current live responses, and result completeness still need validation with your accounts.

**Current coverage: 68 adapter implementations; 51 of 73 captured IDs have an adapter, sometimes with a substitute provider. 22 captured IDs remain unimplemented.** The complete machine-readable inventory is `connector-coverage.json`.

| Remaining transform | What is missing |
|---|---|
| `domain_trademark` | Needs a documented trademark-search API and matching strategy; a trademark record endpoint alone cannot search by domain. |
| `email_linkedin_account` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `email_reverse_lookup` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `email_social_presence` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `email_truepeople` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `facebook_profile_followed` | No corresponding contract in the reviewed ScrapeCreators specification. |
| `facebook_profile_followers` | No corresponding contract in the reviewed ScrapeCreators specification. |
| `facebook_profile_likes` | No corresponding contract in the reviewed ScrapeCreators specification. |
| `gmail_account_presence` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `linkedin_email` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `linkedin_posts` | Needs a documented personal-profile posts API; company posts and keyword post search are implemented separately. |
| `phone_breach_data` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_callapp` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_eyecon` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_social_trace` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_truecaller` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_truepeople` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `phone_whatsapp` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `truepeople_search` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `twitter_popular_tweets` | The documented user-tweets endpoint does not offer a popular sort. Latest/user tweets are implemented; no complete popularity ranking is claimed. |
| `username_breach_data` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |
| `username_reverse_lookup` | The capture identifies an internal transform/class, not a usable upstream URL, authentication scheme, request contract, or provider account entitlement. |

## Contract references used for implementation

- [ScrapeCreators OpenAPI specification](https://docs.scrapecreators.com/openapi.json): routes, input parameters, and cursor response examples. A small contract snapshot is included in the tests.
- [CrewAI Serper implementation](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai-tools/src/crewai_tools/tools/serper_dev_tool/serper_dev_tool.py) and [LangChain Serper implementation](https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/utilities/google_serper.py): provider-recommended library contracts for requests and places. Atlas retains full responses rather than applying their snippet parsers.
- [SecurityTrails IPv4 examples](https://docs.securitytrails.com/docs/examples) and [domain-list reference](https://docs.securitytrails.com/reference/search-old-1).
- [Sightengine content model documentation](https://sightengine.com/docs/models): optional classifications only, with no filtering decisions.
