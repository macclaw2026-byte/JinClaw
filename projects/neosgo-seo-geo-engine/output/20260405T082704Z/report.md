# Neosgo SEO + GEO daily report

- Generated at: 2026-04-05T08:27:04.587148+00:00
- Mode: publish_live
- Publish allowed: True
- API base: https://mc.neosgo.com
- Blocked: False
- Workflow order: sync_google_search_console -> ingest_history_and_feedback -> distill_feedback -> market_research -> adaptive_strategy_selection -> content_execution -> report_and_state_writeback

## Missing requirements / issues
- gsc_sync_failed:token_http_401:{
  "error": "unauthorized_client",
  "error_description": "Unauthorized"
}

## Summary
- Existing notes: 5
- Backlog notes: 4
- Historical feedback rows loaded: 0
- GSC sync: sync_failed
- Primary focus topic: pendant
- Research lead topic: pendant
- Editorial pass count: 4
- Writes this run: 4
- Published note backfills: 0
- Published GEO backfills: 0
- Remaining gaps: 8
- Geo priority order: RI, MA, CT, NH, ME, VT, NY, CA, TX, FL

## Historical feedback distillation
- Feedback rows loaded: 0

## Google Search Console sync
- Not synced: sync_failed

## Market research
- Topic `pendant` | score=2.0 | note_gap=1 | geo_gap=0 | clicks=0.0
- Topic `bathroom` | score=2.0 | note_gap=1 | geo_gap=0 | clicks=0.0
- Topic `chandelier` | score=2.0 | note_gap=1 | geo_gap=0 | clicks=0.0
- Topic `living-room` | score=2.0 | note_gap=1 | geo_gap=0 | clicks=0.0

## Research briefs
- `kitchen-island-pendant-light-spacing-guide` | topic=pendant | angle=priority_reference_guide | problem=The reader wants a confident answer to `kitchen island pendant light spacing` without making an expensive lighting mistake.
  competitor gaps: weak explanation of why proportion fails visually, little guidance on balancing fixture width, island length, and room openness together, minimal transition from educational answer to curated shopping path
- `bathroom-vanity-light-size-guide` | topic=bathroom | angle=decision_guide | problem=The reader wants a confident answer to `bathroom vanity light size guide` without making an expensive lighting mistake.
  competitor gaps: too generic for design-led spaces, weak explanation of flattering facial light versus harsh mirror light, little guidance on choosing between bar fixtures and sconces by room context
- `dining-room-chandelier-size-guide` | topic=chandelier | angle=decision_guide | problem=The reader wants a confident answer to `dining room chandelier size guide` without making an expensive lighting mistake.
  competitor gaps: over-reliance on old formulas without style interpretation, little help for readers choosing visual presence versus restraint, weak differentiation between room-centered and table-centered composition
- `living-room-layered-lighting-guide` | topic=living-room | angle=decision_guide | problem=The reader wants a confident answer to `living room layered lighting guide` without making an expensive lighting mistake.
  competitor gaps: often inspirational instead of decision-oriented, weak connection between fixture planning and actual room use, limited guidance on what not to overdo in layered schemes

## Adaptive strategy
- Topic `pendant` | adaptive_score=1.5 | gap_urgency=1 | fresh_geo_need=0
- Topic `bathroom` | adaptive_score=1.5 | gap_urgency=1 | fresh_geo_need=0
- Topic `chandelier` | adaptive_score=1.5 | gap_urgency=1 | fresh_geo_need=0
- Topic `living-room` | adaptive_score=1.5 | gap_urgency=1 | fresh_geo_need=0

## Editorial quality gate
- `kitchen-island-pendant-light-spacing-guide` | score=87 | passed=True | intent=22 | utility=20 | depth=15
- `bathroom-vanity-light-size-guide` | score=84 | passed=True | intent=22 | utility=18 | depth=14
- `dining-room-chandelier-size-guide` | score=84 | passed=True | intent=22 | utility=18 | depth=14
- `living-room-layered-lighting-guide` | score=84 | passed=True | intent=22 | utility=18 | depth=14

## Writes
- {"kind": "geo_variant_create", "note_id": "cmnjt91pu000410spox3zdpfl", "note_slug": "kitchen-island-pendant-light-spacing-guide", "variantId": "cmnlhzzbn001ahpbkknrjnhsr", "geo_slug": "portland-me", "state": "ME", "status": "DRAFT", "published": true, "publish_result": {"variant": {"id": "cmnlhzzbn001ahpbkknrjnhsr", "noteId": "cmnjt91pu000410spox3zdpfl", "slug": "portland-maine", "geoLabel": "Portland, Maine", "city": "Portland", "state": "ME", "geoGroup": "city", "intentKeyword": "portland kitchen island pendant light spacing", "title": "Kitchen Island Pendant Light Spacing Guide in Portland", "description": "A practical guide to sizing, spacing, and hanging pendant lights over a kitchen island. Localized for Portland, ME.", "quickAnswer": "Pendant spacing over a kitchen island should balance island length, fixture width, and visual breathing room between each light. This version is localized for Portland, ME.", "sections": [{"body": "Use the same sizing and placement logic, while adapting finish, warmth, and visual presence to the design preferences commonly seen in Portland projects.", "heading": "What works well in Portland projects?"}], "faq": [], "seoTitle": null, "seoDescription": null, "ogTitle": null, "ogDescription": null, "canonicalUrl": null, "internalLinks": [], "schemaJsonLd": null, "status": "PUBLISHED", "publishedAt": "2026-04-05T08:27:06.420Z", "createdByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "updatedByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "createdAt": "2026-04-05T08:27:05.747Z", "updatedAt": "2026-04-05T08:27:06.421Z"}}, "public_url": "https://neosgo.com/notes/kitchen-island-pendant-light-spacing-guide/geo/portland-me"}
- {"kind": "geo_variant_create", "note_id": "cmnjt91pu000410spox3zdpfl", "note_slug": "kitchen-island-pendant-light-spacing-guide", "variantId": "cmnli00em001ihpbkbe052uda", "geo_slug": "burlington-vt", "state": "VT", "status": "DRAFT", "published": true, "publish_result": {"variant": {"id": "cmnli00em001ihpbkbe052uda", "noteId": "cmnjt91pu000410spox3zdpfl", "slug": "burlington-vermont", "geoLabel": "Burlington, Vermont", "city": "Burlington", "state": "VT", "geoGroup": "city", "intentKeyword": "burlington kitchen island pendant light spacing", "title": "Kitchen Island Pendant Light Spacing Guide in Burlington", "description": "A practical guide to sizing, spacing, and hanging pendant lights over a kitchen island. Localized for Burlington, VT.", "quickAnswer": "Pendant spacing over a kitchen island should balance island length, fixture width, and visual breathing room between each light. This version is localized for Burlington, VT.", "sections": [{"body": "Use the same sizing and placement logic, while adapting finish, warmth, and visual presence to the design preferences commonly seen in Burlington projects.", "heading": "What works well in Burlington projects?"}], "faq": [], "seoTitle": null, "seoDescription": null, "ogTitle": null, "ogDescription": null, "canonicalUrl": null, "internalLinks": [], "schemaJsonLd": null, "status": "PUBLISHED", "publishedAt": "2026-04-05T08:27:07.843Z", "createdByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "updatedByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "createdAt": "2026-04-05T08:27:07.150Z", "updatedAt": "2026-04-05T08:27:07.844Z"}}, "public_url": "https://neosgo.com/notes/kitchen-island-pendant-light-spacing-guide/geo/burlington-vt"}
- {"kind": "geo_variant_create", "note_id": "cmnjt920c000910spywql628j", "note_slug": "bathroom-vanity-light-size-guide", "variantId": "cmnli01rm001qhpbk49cto7kb", "geo_slug": "austin-tx", "state": "TX", "status": "DRAFT", "published": true, "publish_result": {"variant": {"id": "cmnli01rm001qhpbk49cto7kb", "noteId": "cmnjt920c000910spywql628j", "slug": "austin-texas", "geoLabel": "Austin, Texas", "city": "Austin", "state": "TX", "geoGroup": "city", "intentKeyword": "austin bathroom vanity light size guide", "title": "Bathroom Vanity Light Size Guide in Austin", "description": "A sizing guide for bathroom vanity lighting with practical placement and proportion advice. Localized for Austin, TX.", "quickAnswer": "Vanity lighting should feel proportionate to the mirror width and provide even facial illumination without harsh glare. This version is localized for Austin, TX.", "sections": [{"body": "Use the same sizing and placement logic, while adapting finish, warmth, and visual presence to the design preferences commonly seen in Austin projects.", "heading": "What works well in Austin projects?"}], "faq": [], "seoTitle": null, "seoDescription": null, "ogTitle": null, "ogDescription": null, "canonicalUrl": null, "internalLinks": [], "schemaJsonLd": null, "status": "PUBLISHED", "publishedAt": "2026-04-05T08:27:09.596Z", "createdByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "updatedByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "createdAt": "2026-04-05T08:27:08.914Z", "updatedAt": "2026-04-05T08:27:09.597Z"}}, "public_url": "https://neosgo.com/notes/bathroom-vanity-light-size-guide/geo/austin-tx"}
- {"kind": "geo_variant_create", "note_id": "cmnjt920c000910spywql628j", "note_slug": "bathroom-vanity-light-size-guide", "variantId": "cmnli02tl001yhpbkjc8i7hu1", "geo_slug": "miami-fl", "state": "FL", "status": "DRAFT", "published": true, "publish_result": {"variant": {"id": "cmnli02tl001yhpbkjc8i7hu1", "noteId": "cmnjt920c000910spywql628j", "slug": "miami-florida", "geoLabel": "Miami, Florida", "city": "Miami", "state": "FL", "geoGroup": "city", "intentKeyword": "miami bathroom vanity light size guide", "title": "Bathroom Vanity Light Size Guide in Miami", "description": "A sizing guide for bathroom vanity lighting with practical placement and proportion advice. Localized for Miami, FL.", "quickAnswer": "Vanity lighting should feel proportionate to the mirror width and provide even facial illumination without harsh glare. This version is localized for Miami, FL.", "sections": [{"body": "Use the same sizing and placement logic, while adapting finish, warmth, and visual presence to the design preferences commonly seen in Miami projects.", "heading": "What works well in Miami projects?"}], "faq": [], "seoTitle": null, "seoDescription": null, "ogTitle": null, "ogDescription": null, "canonicalUrl": null, "internalLinks": [], "schemaJsonLd": null, "status": "PUBLISHED", "publishedAt": "2026-04-05T08:27:10.947Z", "createdByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "updatedByUserId": "cmlg0yg7k0001bb7d9fcg59k3", "createdAt": "2026-04-05T08:27:10.282Z", "updatedAt": "2026-04-05T08:27:10.948Z"}}, "public_url": "https://neosgo.com/notes/bathroom-vanity-light-size-guide/geo/miami-fl"}

## Gaps
- {"type": "missing_geo_variant", "note_slug": "kitchen-island-pendant-light-spacing-guide", "geo_slug": "portland-me", "state": "ME"}
- {"type": "missing_geo_variant", "note_slug": "kitchen-island-pendant-light-spacing-guide", "geo_slug": "burlington-vt", "state": "VT"}
- {"type": "missing_geo_variant", "note_slug": "bathroom-vanity-light-size-guide", "geo_slug": "austin-tx", "state": "TX"}
- {"type": "missing_geo_variant", "note_slug": "bathroom-vanity-light-size-guide", "geo_slug": "miami-fl", "state": "FL"}
- {"type": "missing_geo_variant", "note_slug": "dining-room-chandelier-size-guide", "geo_slug": "austin-tx", "state": "TX"}
- {"type": "missing_geo_variant", "note_slug": "dining-room-chandelier-size-guide", "geo_slug": "miami-fl", "state": "FL"}
- {"type": "missing_geo_variant", "note_slug": "living-room-layered-lighting-guide", "geo_slug": "austin-tx", "state": "TX"}
- {"type": "missing_geo_variant", "note_slug": "living-room-layered-lighting-guide", "geo_slug": "miami-fl", "state": "FL"}
