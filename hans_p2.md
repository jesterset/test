# Canada Politics MCP — Canonical API and Open Data Links

## Purpose

This document lists the canonical public URLs surfaced during research for the Canada politics intelligence MCP. It includes direct API bases where available and canonical open-data or transcript entry points where a source is not exposed as a traditional REST API.[cite:2][cite:8][cite:16][cite:27][cite:32][cite:62]

## Federal

| Source | Access type | Canonical URL | Notes |
|---|---|---|---|
| House of Commons Open Data | Open-data portal | [https://www.ourcommons.ca/en/open-data](https://www.ourcommons.ca/en/open-data) | Canonical federal entry point for House open data and official machine-readable publications.[cite:8] |
| House of Commons Open Data Glossary | Schema / format reference | [https://www.ourcommons.ca/en/open-data/glossary](https://www.ourcommons.ca/en/open-data/glossary) | Useful for understanding official publication schemas and formats.[cite:60] |
| OpenParliament API | API base | [https://openparliament.ca/api/](https://openparliament.ca/api/) | Developer-friendly API for bills, votes, MPs, debates, and committees.[cite:2] |
| OpenParliament main site | Human-readable entry point | [https://openparliament.ca](https://openparliament.ca) | Useful for source inspection and link traversal alongside the API.[cite:31] |
| LiPaD main site | Historical parliamentary data portal | [https://www.lipad.ca](https://www.lipad.ca) | Linked Parliamentary Data Project portal.[cite:3] |
| LiPaD data page | Historical data entry point | [https://www.lipad.ca/data/](https://www.lipad.ca/data/) | Canonical page for dumps, CSV, XML, and related data resources.[cite:49] |
| Canadian Parliamentary Historical Resources | Historical archive portal | [https://parl.canadiana.ca](https://parl.canadiana.ca) | Historical parliamentary materials and scans.[cite:73] |

## Provinces and Territories

| Source | Jurisdiction | Access type | Canonical URL | Notes |
|---|---|---|---|---|
| Legislative Assembly of Ontario House Documents | Ontario | Open legislative portal | [https://www.ola.org/en/legislative-business/house-documents](https://www.ola.org/en/legislative-business/house-documents) | Canonical entry point for Hansard, Orders and Notices, Votes and Proceedings, and related House materials.[cite:62] |
| Ontario Hansard Search | Ontario | Search entry point | [https://www.ola.org/en/legislative-business/hansard-search](https://www.ola.org/en/legislative-business/hansard-search) | Canonical search page for Ontario Hansard content.[cite:78] |
| Manitoba Hansard | Manitoba | Official transcript portal | [https://www.gov.mb.ca/legislature/hansard/hansard.html](https://www.gov.mb.ca/legislature/hansard/hansard.html) | Current House and committee debates, with transcript and video access.[cite:59][cite:92] |
| Manitoba Hansard Archive / Index | Manitoba | Archive portal | [https://www.gov.mb.ca/legislature/hansard/hansard_archive.html](https://www.gov.mb.ca/legislature/hansard/hansard_archive.html) | Archive and index entry point for historical Manitoba Hansard sessions.[cite:89] |
| Journal des débats — Assemblée nationale du Québec | Québec | Official debates portal | [https://www.assnat.qc.ca/fr/travaux-parlementaires/journaux-debats.html](https://www.assnat.qc.ca/fr/travaux-parlementaires/journaux-debats.html) | Official Québec debates transcription access page.[cite:91] |
| Journal des débats information page | Québec | Official reference page | [https://www.assnat.qc.ca/en/publications/fiche-journal-debats.html](https://www.assnat.qc.ca/en/publications/fiche-journal-debats.html) | Official description page for the Québec Hansard equivalent.[cite:76] |
| Érudit dataset documentation for Québec debates | Québec | Structured dataset documentation | [https://datasets.docs.erudit.org/i18n/en/datasets/assnatqc_journal_debats.html](https://datasets.docs.erudit.org/i18n/en/datasets/assnatqc_journal_debats.html) | Structured dataset documentation for Québec parliamentary debates.[cite:50] |
| Open NWT API | Northwest Territories | API base | [https://hansard.opennwt.ca/api/](https://hansard.opennwt.ca/api/) | API for bills, votes, MLAs, debates, and committees.[cite:32] |

## Municipal

| Source | Jurisdiction | Access type | Canonical URL | Notes |
|---|---|---|---|---|
| Toronto Notices Open Data API | Toronto | API / open-data endpoint | [https://secure.toronto.ca/nm/opendata.do](https://secure.toronto.ca/nm/opendata.do) | Canonical City Clerk notices endpoint surfaced for real-time notices and filtered retrieval.[cite:16] |
| Vancouver Council Voting Records API | Vancouver | Open-data API endpoint | [https://opendata.vancouver.ca/explore/dataset/council-voting-records/api/](https://opendata.vancouver.ca/explore/dataset/council-voting-records/api/) | Canonical API page for council voting records.[cite:27] |
| Vancouver Council Voting Records dataset page | Vancouver | Dataset portal | [https://opendata.vancouver.ca/explore/dataset/council-voting-records/](https://opendata.vancouver.ca/explore/dataset/council-voting-records/) | Human-readable dataset page paired with the API endpoint.[cite:30] |

## Geography and Prioritization

| Source | Access type | Canonical URL | Notes |
|---|---|---|---|
| Statistics Canada CMA population estimates | National statistical table | [https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014801](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014801) | Useful for census metropolitan area hierarchy, national place normalization, and rollout prioritization.[cite:45] |

## Practical Notes

Some of these sources are true APIs, while others are canonical open-data, transcript, search, or archive entry points that should still be treated as first-class ingest sources for the MCP.[cite:2][cite:8][cite:16][cite:27][cite:62]

For implementation, it is best to store each source with fields such as `name`, `jurisdiction`, `access_type`, `canonical_url`, `formats`, `entity_types`, `freshness`, and `adapter_name` so the registry can drive ingestion and retrieval consistently.[cite:2][cite:49][cite:60]
