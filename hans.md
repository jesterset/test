# Canada Politics Intelligence MCP — Product Requirements Document

## Overview

This product is a Model Context Protocol (MCP) server that gives executives, strategy teams, public affairs teams, researchers, and assistants a place-aware view of Canadian politics across federal, provincial or territorial, and municipal layers.[cite:2][cite:8][cite:16][cite:27]

The core job of the product is to answer questions such as: what is happening in a city or region now, which actors matter, what decisions are pending, and how a large institution such as a bank may be implicated directly through its business lines or indirectly through local civic context.[cite:2][cite:8][cite:16][cite:27]

The product should not be built as a generic “search all politics” tool first. It should be built as a briefing and decision-support engine that can search, normalize, rank, and summarize public political records into concise, auditable intelligence products.[cite:2][cite:8][cite:49]

## Problem Statement

Canadian political data is open, but it is fragmented across multiple jurisdictions, formats, and publication styles.[cite:8][cite:16][cite:27][cite:60]

At the federal level, official House of Commons open data exposes debates, votes, committee evidence, petitions, member data, and bill information, while OpenParliament offers a more developer-friendly API over major parliamentary objects.[cite:8][cite:2]

At the provincial and territorial level, legislatures publish their own Hansard or house-document systems, such as Ontario House documents, Manitoba Hansard, Québec debate archives, and the Northwest Territories API.[cite:62][cite:59][cite:50][cite:32]

At the municipal level, the data surface is even more fragmented, with city-specific datasets such as Toronto Clerk notices and Vancouver council voting records rather than a single national standard.[cite:16][cite:27]

Users who need a fast political readout before a meeting, trip, announcement, or stakeholder engagement should not have to manually navigate dozens of sites and formats.[cite:8][cite:16][cite:27]

## Product Vision

The product should become the canonical MCP for Canadian political context. It should let an LLM or application ask for a place, issue, actor, or institution and receive structured, cited, current results with clear provenance.[cite:2][cite:8][cite:16][cite:27]

The most valuable use case is executive travel and stakeholder briefing. For example, a bank CEO visiting Calgary, Montréal, Halifax, or Vancouver should be able to ask what is politically live, who the key actors are, which issues are most salient, and where the institution is likely to matter commercially, civically, or reputationally.[cite:45][cite:16][cite:27]

## Goals

- Deliver a unified MCP interface across Canadian federal, provincial or territorial, and municipal political data sources.[cite:8][cite:2][cite:62][cite:32][cite:16][cite:27]
- Normalize heterogeneous source formats including XML, JSON, CSV, and RSS into one retrieval and ranking layer.[cite:8][cite:49][cite:60]
- Produce place-aware briefings for executives, public affairs teams, and researchers.[cite:45][cite:16][cite:27]
- Preserve traceability by linking every normalized object back to the original public record.[cite:2][cite:8]
- Support both “inside the box” business implications and “outside the box” civic, reputational, and partnership implications for a named institution.[cite:8][cite:16][cite:27]

## Non-Goals

- Replacing primary legal, legislative, or compliance advice.
- Predicting election outcomes or legislative passage with certainty.
- Covering every municipality in Canada in v1.
- Acting as a partisan persuasion tool.
- Storing private or non-public political intelligence.

## Users and Use Cases

### Primary users

- CEOs and executive offices that need pre-visit or pre-meeting local political context.
- Public affairs, government relations, and communications teams that need issue tracking and actor mapping.
- Strategy and market intelligence teams that need local policy context tied to business themes.
- Researchers or journalists who want one interface over open Canadian political sources.[cite:2][cite:8][cite:49]

### Core use cases

1. **Place briefing**: “What is going on politically in Vancouver this week that matters to a national bank?”[cite:27][cite:45]
2. **Issue tracking**: “Show recent debate, committee, and city signals related to housing affordability in Toronto.”[cite:8][cite:16]
3. **Actor analysis**: “Who are the most salient elected officials connected to transit funding in Montréal?”[cite:2][cite:50]
4. **Decision watch**: “What upcoming notices, votes, or house proceedings in Ontario could affect small-business lending or housing supply?”[cite:62][cite:16]
5. **Institution lens**: “Where could RBC matter directly through business lines and indirectly through community or public-interest activity in Halifax?”[cite:45]

## Scope

### Jurisdictional scope

The system must support three layers of political context:

- **Federal**: House of Commons open data, parliamentary debates, votes, committees, petitions, bills, and normalized parliamentary API access.[cite:8][cite:2]
- **Provincial and territorial**: legislature-specific Hansard, house documents, committee records, votes, and related open records where available.[cite:62][cite:59][cite:50][cite:32]
- **Municipal**: city open-data feeds and council artifacts such as notices, agendas, voting records, minutes, and public-hearing records where available.[cite:16][cite:27]

### Geographic scope

The product should be national in ambition but tiered in rollout. Statistics Canada’s census metropolitan area hierarchy should be used to define the initial place map and priority metros, while capitals and economically important regional centers should be layered in even where they are smaller than the largest CMAs.[cite:45]

## Source Inventory

### Federal sources

| Source | Type | Primary value |
|---|---|---|
| House of Commons Open Data | Official federal open data | MPs, roles, constituencies, party standings, ministers, votes, debates, committee evidence, petitions, bill data via LEGISinfo, publication search, expenditures.[cite:8] |
| OpenParliament API | Normalized federal API | Bills, votes, MPs, debates, committees, linked objects, developer-friendly resource graph.[cite:2] |
| LiPaD | Historical parliamentary data | PostgreSQL dump, daily UTF-8 CSV, XML Hansard from 1901 to 1993, party and politician data, and links to historical parliamentary material.[cite:49] |

### Provincial and territorial sources

| Source | Type | Primary value |
|---|---|---|
| Legislative Assembly of Ontario House Documents | Official provincial legislature site | Hansard, Orders and Notices, Votes and Proceedings, Hansard search, Hansard index, and related House records.[cite:62] |
| Manitoba Hansard | Official provincial legislature site | House debates, committee debates, question period, votes and proceedings, order paper, bill status, and legislative committees.[cite:58][cite:59] |
| Journal des débats of the National Assembly of Québec | Debate corpus / structured dataset | Québec debate archive for provincial political speech and issue tracking.[cite:50] |
| Open NWT API | Territorial legislature API | Bills, votes, MLAs, debates, committees, and related territory legislative objects.[cite:32] |

### Municipal sources

| Source | Type | Primary value |
|---|---|---|
| Toronto Notices Open Data API | Municipal open-data API | Real-time City Clerk notices and filterable notice retrieval for upcoming and recent city business.[cite:16] |
| Vancouver Council Voting Records | Municipal open-data dataset / API | Council, Special Council, Standing Committee, and Public Hearing voting records after minutes are published.[cite:27] |

### Geography and place sources

| Source | Type | Primary value |
|---|---|---|
| Statistics Canada CMA population estimates | National geography and prioritization layer | Metro hierarchy, coverage planning, and place normalization for national rollout.[cite:45] |

## Data Requirements

### Canonical entities

The MCP should normalize all sources into a shared model built around the following entities:[cite:2][cite:8][cite:16][cite:27]

- `Place`: city, metro, riding, province, territory, country.
- `Actor`: MP, MLA, MPP, councillor, mayor, committee chair, minister, parliamentary secretary, caucus leader, or institution-linked actor.
- `Issue`: canonical public-policy topic such as housing, transit, public safety, climate, banking, procurement, immigration, affordability, or Indigenous relations.
- `Event`: debate intervention, committee meeting, notice, public hearing, agenda item, petition, press activity, or consultation signal.
- `Decision`: vote, bill stage advancement, adopted motion, rejected motion, by-law approval, committee recommendation, or House proceeding.
- `SourceDocument`: the original public record, transcript, XML document, API object, CSV row group, or meeting artifact.
- `Organization`: optional institutional lens such as RBC, a developer, a chamber of commerce, or a labor group.

### Canonical schemas

Each normalized object should include:

- Stable internal ID.
- Original source URL or source identifier.[cite:2][cite:8]
- Jurisdiction and sub-jurisdiction.
- Date and time fields when available.
- Entity references to place, actor, issue, decision, and document.
- Classification tags for theme, subtheme, stage, and salience.
- An auditable excerpt or summary with provenance.

### Format requirements

The ingestion layer must support XML, JSON, CSV, and RSS because the federal parliamentary ecosystem alone exposes multiple formats across debates, votes, petitions, and bill data.[cite:8][cite:60][cite:49]

## Functional Requirements

### MCP tools

The initial MCP should expose the following tools:

1. `resolve_place(query, include_layers)`
2. `brief_place(place_id, date_range, themes, audience)`
3. `search_events(place_ids, query, event_kinds, date_range)`
4. `list_actors(place_id, issue_id, limit)`
5. `get_actor_profile(actor_id)`
6. `track_issue(issue_id, place_ids, date_range)`
7. `organization_angle(organization_id, place_id, issue_ids, mode)`
8. `source_lookup(source_document_id)`

### Tool behavior

- `resolve_place` must convert city, postal code, metro, riding, province, or territory input into canonical place IDs backed by jurisdiction metadata.[cite:45][cite:32]
- `brief_place` must return live issues, top actors, recent decisions, watch items, and institution-specific angles.[cite:8][cite:16][cite:27]
- `search_events` must search across normalized debates, notices, votes, committee records, and municipal signals.[cite:8][cite:2][cite:16][cite:27]
- `get_actor_profile` must return office, jurisdiction, party or caucus affiliation where relevant, recent appearances, and decision participation history.[cite:8][cite:2]
- `source_lookup` must always expose the original public record URL and enough metadata to let the user audit the answer.[cite:2][cite:8]

### Output requirements

Each tool response should be:

- Structured JSON.
- Citation-ready.
- Explicit about time range.
- Explicit about source freshness.
- Safe for direct consumption by LLMs.
- Deterministic enough for downstream application use.

## Briefing Logic

The product should rank signals by a blend of freshness, place relevance, issue relevance, actor salience, decision weight, and institution fit.[cite:8][cite:16][cite:27]

A place briefing should contain:

- **What is happening now**: recent and upcoming debates, notices, votes, committee activity, and hearings.[cite:8][cite:16][cite:27]
- **Who matters**: elected officials and institutional actors most connected to those signals.[cite:2][cite:8]
- **Why it matters**: issue tags and plain-language implication summaries.
- **Institution lens**: inside-the-box business implications, outside-the-box civic or reputational implications, and potential watchouts.
- **Audit trail**: source links back to official or well-established public records.[cite:2][cite:8]

## Source Adapter Requirements

### Adapter pattern

The system should use one adapter per source family rather than one universal scraper. This is required because the surfaced Canadian political ecosystem spans official XML publications, JSON APIs, downloadable CSV or database exports, and city-specific open-data datasets.[cite:8][cite:49][cite:16][cite:27][cite:60]

### Initial adapters

- `federal_house`
- `federal_openparliament`
- `federal_lipad`
- `province_ontario`
- `province_manitoba`
- `province_quebec`
- `territory_nwt`
- `municipal_toronto`
- `municipal_vancouver`
- `geography_statcan`

### Adapter obligations

Every adapter must provide:

- Source metadata.
- Health and freshness status.
- Pagination or crawl strategy.
- Normalization mapping.
- Provenance mapping from normalized object to original source URL.[cite:2][cite:8]
- Error handling for schema drift.

## Ranking and Classification

### Issue taxonomy

The product should ship with a canonical issue taxonomy that includes at minimum:

- Housing and affordability.
- Small business and local economic development.
- Commercial real estate and land use.
- Transit and infrastructure.
- Public safety.
- Climate and resilience.
- Immigration and newcomer integration.
- Health and social services.
- Indigenous relations.
- Procurement and public spending.

These issues are broad enough to span debates, votes, notices, and city council activity while staying useful for institution-level briefings.[cite:8][cite:16][cite:27]

### Relevance scoring

The first scoring model should include:

- Freshness.
- Place match.
- Issue match.
- Actor salience.
- Decision weight.
- Organization fit.

The scoring model should be explainable and inspectable because the product is intended for high-trust executive and public-affairs workflows.

## Non-Functional Requirements

### Auditability

Every answer must be traceable to the original public record, whether that record came from official House XML, a legislature house-document page, or a municipal open-data dataset.[cite:8][cite:62][cite:16][cite:27]

### Freshness

The system should support scheduled ingestion, incremental refresh, and freshness metadata because several surfaced sources publish current or near-current parliamentary and municipal activity.[cite:8][cite:16][cite:27]

### Reliability

The system must tolerate partial source outages and schema changes. A failed municipal adapter should not break federal or provincial retrieval.

### Security and privacy

The system should ingest only public open sources in v1. It should not require private lobbying data, private calendars, leaked documents, or paid data dependencies.

### Bilingual support

The system should support English and French ingestion and retrieval where sources expose French-language parliamentary or municipal records, especially for Québec and federal parliamentary materials.[cite:8][cite:50]

## UX and Product Surfaces

### Primary surfaces

- MCP for LLM clients.
- CLI for debugging and internal analyst use.
- Optional dashboard for source health, ingestion status, and search validation.
- Optional executive briefing output in Markdown or HTML.

### Core response shapes

The product should support at least four response forms:

- **Briefing**: concise place or issue summary.
- **Timeline**: chronological view of events and decisions.
- **Actor map**: actors connected to an issue or place.
- **Source dossier**: raw or lightly normalized source records for audit and research.

## Rollout Plan

### Phase 1

Build the federal backbone first with House of Commons Open Data, OpenParliament, LiPaD, and Statistics Canada geography.[cite:8][cite:2][cite:49][cite:45]

### Phase 2

Add one province, one territory, and two municipalities with distinct patterns: Ontario, Northwest Territories, Toronto, and Vancouver are strong early adapters because the surfaced sources show different but useful publication models.[cite:62][cite:32][cite:16][cite:27]

### Phase 3

Add Manitoba and Québec for broader provincial coverage and bilingual or historical depth.[cite:58][cite:59][cite:50]

### Phase 4

Expand by place priority, using Statistics Canada’s CMA hierarchy plus provincial and territorial capitals and institution-specific regional hubs.[cite:45]

## Success Metrics

### Product metrics

- Median time to first useful briefing.
- Share of answers with at least one official-source citation.
- Coverage of prioritized metros and capitals.
- Freshness SLA by source family.
- Precision of top-ranked issues in analyst review.
- Percentage of normalized objects with valid provenance links.

### User outcomes

- Executives report better pre-visit situational awareness.
- Public-affairs teams report less manual source-hopping.
- Analysts can move from question to source document quickly.

## Risks and Mitigations

| Risk | Description | Mitigation |
|---|---|---|
| Source fragmentation | Canada’s political data is distributed across many source systems and formats.[cite:8][cite:16][cite:27][cite:60] | Adapter-based architecture, canonical schemas, source registry. |
| Schema drift | Official XML or site structures can change over time.[cite:8][cite:62] | Versioned parsers, schema monitoring, regression tests. |
| Municipal inconsistency | City-level datasets vary widely in depth and structure.[cite:16][cite:27] | Start with high-value city adapters and standardized normalized outputs. |
| Over-summarization | LLM-generated summaries can blur nuance from the source record. | Preserve excerpts, source links, and structured evidence blocks. |
| Bilingual complexity | Federal and Québec records can require French support.[cite:8][cite:50] | Language detection, bilingual normalization fields, translation as a presentation layer. |

## Open Questions

- Which institution profiles should be first-class beyond a bank use case?
- Should the system treat provinces and territories as separate adapter families or as one legislature abstraction with per-source mappings?
- How much municipal breadth is required before the product is considered nationally credible?
- Should the first release include dashboards, or remain MCP-first and CLI-first?
- What ranking feedback loop should be used to tune relevance for executive briefings?

## Recommended v1 Decision

The recommended v1 is an MCP-first product with a federal backbone, a small but representative set of province, territory, and city adapters, a canonical place and issue model, and a briefing-oriented API surface.[cite:8][cite:2][cite:62][cite:32][cite:16][cite:27]

That shape maximizes usefulness early, stays grounded in open public records, and creates a clean path to broader national coverage over time.[cite:45][cite:49]
