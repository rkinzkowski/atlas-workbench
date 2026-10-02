# WebVetted feature coverage — 2026-09-19

This is a gap register, not a claim of complete parity. The captures establish browser-visible workflows and a catalog of 73 transform IDs; they do not expose the entire product, upstream APIs, full report algorithm or source entitlements. Atlas currently implements 68 adapters, including alternatives and additions: 51 captured IDs have an adapter and 22 do not. Limited live account testing includes one successful ScrapeCreators public Instagram profile, a private-profile failure, and a Serper free-account query rejection; other paid routes remain unvalidated. See VALIDATION.md. Free/local replacement candidates are assessed in [FREE-SOURCE-COMPARISON.md](FREE-SOURCE-COMPARISON.md); they do not change the implemented count.

## Captured workflows

| Capability | Atlas status | Qualification |
|---|---|---|
| Multiple investigations and typed seeds | Implemented | Persistent local cases and standalone lookups |
| Case and node updates | Implemented | Previous node details retained in Activity; source records unchanged |
| Related nodes and evidence-linked graph edges | Implemented | Manual and extracted leads; no automatic identity verification |
| Node, case and answer removal | Implemented differently | Reversible Trash rather than permanent deletion |
| Graph drag/pan/zoom/save/reset | Implemented | Positions and viewport persist |
| Transform execution and retry | Implemented | Explicit retries; interrupted charged calls do not auto-replay |
| Retry extraction and apply selected entities | Implemented | Full source fields retained even when extraction has no mapping |
| Internal collection / graph / deeper graph / web / report phases | Implemented | Bounded deterministic workflow; selected sources and shared budget determine actual execution |
| Evidence vault and original IDs/provenance | Implemented | Full stored fields, hashes, review state, notes and downloads |
| Case questions and cited answers | Implemented | Full-field search; optional OpenAI answers; Hermes-authored answers can be stored through the bridge |
| Versioned report regeneration and export | Implemented | Complete evidence report plus optional interpretation; exact proprietary forensic report not captured |
| Node monitors, pause, interval, removal | Implemented locally | Runs while server is up; changed responses linked to comparisons |
| Walkthrough/help | Basic guide implemented | Does not replicate WebVetted's unknown tutorial telemetry/progression |
| Social-report / reverse-intelligence imports | Partially covered | Evidence arrays and captured investigation/HAR/Atlas formats work; unprovided proprietary report shapes remain unverified |
| Agent clarifications / autonomous reasoning | Not equivalent | Local planner records scope; actual reasoning can be provided by existing Hermes later; Varda clarification examples were absent |
| Cross-seed matching/identity scoring | Not equivalent | Identifier deduplication and evidence links exist; no unvalidated identity-confidence formula |

## Publicly advertised capabilities beyond the captured workflow

WebVetted advertises cross-source lookup and alerts on its [reverse lookup page](https://webvetted.com/detect/lookup), and account-integrity, engagement, image and other checks on its [social intelligence page](https://webvetted.com/detect/social). Those are product claims, not confirmed upstream contracts or independent validation.

| Capability | Current boundary |
|---|---|
| Hundreds of upstream data sources | Atlas retains the complete payload returned by each connected provider; adapter count is not the number of upstream datasets. No claim of matching WebVetted's source coverage. |
| Phone/email/name/username and social lookup | Working workflows and documented provider adapters; exact private-source parity still has the gaps below. |
| Reverse image and image classifications | Documented image-URL adapters; no verified equivalence to all proprietary image/deepfake models. |
| Account integrity, fake followers, impersonation/fraud scoring | Returned source metrics are retained. No independently validated equivalent scoring model is implemented. |
| Continuous monitoring and instant notifications | Local scheduled refresh and in-app change evidence exist. Hosted uptime and email/push notification delivery are not implemented. |
| Branded PDF/JSON dossiers | Complete JSON, versioned printable HTML/browser PDF work. No claim that an export establishes forensic admissibility. |
| Subscription credits, hosted priority queues, stealth tier | Not reproduced; Atlas uses the user's provider accounts. No proprietary billing or unspecified stealth behavior is claimed. |

## Additional Atlas capabilities

Complete field visibility and search; complete evidence reports without excerpt substitution; source-to-source comparison with full values; Windows-encrypted key persistence; a readiness screen; reversible Trash preserving evidence; online complete-workspace backups with safe restore; and a 21-tool MCP bridge prepared for Hermes.

## Captured transform gaps

Adding API keys alone does not implement the following 22 missing contracts. Obtain actual vendor documentation and field entitlements before adding them; similarly named substitutes are not exact parity.

| Captured transform | Missing contract or functionality |
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

## Release acceptance still outstanding

- Test each purchased provider with known user-selected identifiers, including no-match and permission-error cases.
- Check returned personal fields against the user's own known facts and record supported/disputed/unresolved findings with citations.
- Capture/document the missing private provider contracts, full Varda report format, active clarification behavior and proprietary social-analysis output before claiming equivalence.
- Integrate with the user's Hermes/BT host later, as requested, and validate real tools in that runtime.

The current application is usable with supported keys. “No missing WebVetted features” is not an achieved or verified release claim.
