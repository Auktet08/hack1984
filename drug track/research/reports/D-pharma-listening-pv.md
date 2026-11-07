# Target D: pharma social listening and pharmacovigilance (research report)

Run: 2026-11-07, `who: claude-D`. Plan: `research/plans/D-pharma-listening-pv.md`. Research only; nothing installed.
Raw files: `research/raw/{tavres-D-1,tavres-D-2,tav-D-1,tavext-D-1,gh-D,D-merged}.json`, `research/raw/exa-D-{1..13}.json`.

**Read this first.** Both Tavily Research mini reports had many wrong license and benchmark claims. Examples: CADEC
"CC-BY-4.0" (it is the CSIRO Data Licence, research-only), MedDialog "Apache-2.0" (the data belongs to the source
websites, whose terms forbid scraping), Loughran-McDonald "CC-BY-4.0" (free for academic use only), Arctic-ABSA "1.2B
Apache" (the paper reports a 395M encoder and an 8B decoder, with no weight release stated), t2t-ner-ade "71.98 strict F1"
(its README reports 0.398), and a "Clinical Speaker-Role Tagger, 0.91, CC-BY code" (the paper is CC BY-NC-ND, reports
82%, and releases no model). Every verdict below rests on a README, dataset card, licence page or paper fetched in this
run, or on the GitHub/HF API, not on the Tavily report text.

## Top picks

| # | Pick | Form | Feeds | Effort |
|---|---|---|---|---|
| 1 | **PsyTAR** sentence labels (ADR / WD / EF / INF) | c | efficacy + safety polarity in patient voice, transcript path | ~2 h |
| 2 | **ICH E2D(R1) four minimum criteria** as an "AE-triage" flag | a/b | safety aspect, demo, pitch | 1–2 h |
| 3 | **ACI-Bench + PriMock57** as speaker-tagged scaffolds for mock transcripts | c | demo, transcript testing, speaker mapping | 1–2 h |
| 4 | **Hedge lexicon** (words/hedges MIT + Hanauer clinical hedge phrases) | b | `evidence_quality` cues on transcripts | ~1 h |
| 5 | **Text-only speaker-role heuristics** (moderator hand-off, self-ID, roster match, else "unknown") | a/b | speaker mapping on transcripts | 2–3 h |

### 1. PsyTAR (adopt)
- **What:** 891 askapatient.com reviews of 4 psychiatric drugs, split into 6,009 sentences. Each sentence is labelled
  ADR, withdrawal (WD), sign/symptom (SSI), indication (DI), **effectiveness (EF)**, **ineffectiveness (INF)** or other.
  It also has 4,813 ADR entity mentions with UMLS/SNOMED links and severity/persistence qualifiers.
- **License:** CC BY 4.0 (paper, PMC6495095; HF `bigbio/psytar` tag cc-by-4.0, not gated). No DUA. The HF loader is a
  script, so take the xlsx from the paper's Online Supplement #1.
- **Use:** pick ~10–20 sentences (EF+, INF−, ADR−, "no side effects"+) as few-shot examples of patient voice for
  efficacy and safety polarity in the Qwen prompt on the transcript path. The sentence labels also give a small offline
  test of the transcript path's polarity on patient text, with no teacher needed.
- **Expected effect:** little on the leaderboard (the test set has little patient text). It mainly makes the safety and
  efficacy calls on mock transcripts more believable.
- **Risks:** psychiatric drugs and consumer language, not oncology. Run the R6 dedupe anyway (expect 0 overlap).
- **Test:** run the transcript path on 100 held-out PsyTAR sentences, with and without the few-shots, and report
  EF/INF/ADR polarity agreement.

### 2. ICH E2D(R1) minimum-criteria AE triage (adopt for the demo and pitch)
- **What:** an ICSR needs ≥1 AE/ADR, ≥1 suspect product, an identifiable patient and an identifiable reporter
  (E2D(R1) §2.2). E2D(R1) §2.8 names MAH **social/digital listening and product sentiment analysis** as examples of an
  organised data collection system (ODCS). AEs found while reviewing that data are managed as solicited reports, and
  **day zero is the moment the reviewer identifies an AE that meets the minimum criteria** (§4.3.2). EMA GVP Module VI
  Rev 2 §VI.B.1.1.4 has the matching EU rule.
- **Use:** when `safety` is non-neutral on a transcript or listening item, add a 4-box checklist (AE quote ✓, product ✓,
  patient cue such as "my mother"/"a patient of mine", reporter = speaker role) and a badge "potential reportable AE:
  route to PV within the reporting clock". Each box points to the verbatim quote that fills it. This is pure rules on
  output we already produce.
- **Risks:** it is not legal advice. Word it as "triage candidate", never "reportable".
- **Demo moment:** a mock advisory-board turn where an HCP mentions a patient's rash on the product turns on all four
  boxes and the badge appears.

### 3. Mock-transcript scaffolds: ACI-Bench + PriMock57 (adopt for structure, not content)
- **ACI-Bench** (github.com/wyim/aci-bench): CC BY 4.0 (README, fetched). 207 doctor-patient conversations with
  `[doctor]`/`[patient]` tags and visit notes. Some ASR speaker tags were deliberately left swapped, which makes a good
  speaker-mapping stress test. Last push 2026-01.
- **PriMock57** (github.com/babylonhealth/primock57): LICENSE.md is CC BY 4.0 (GitHub API shows NOASSERTION, but the
  file is CC BY 4.0). 57 mock primary-care consults with utterance-level manual transcripts.
- Also usable: Fareez et al. 2022 Sci Data, 272 simulated OSCE-style interviews (78.7% respiratory) on figshare
  (CC BY 4.0, per the HF repack `wmatbooth/...-272`, which is **gated: manual**; take it from figshare instead).
- **Use:** copy the turn format and the role mix. Write our oncology/EGFR transcripts (HCP advisory board, MSL notes,
  patient interview) synthetically on top. Use the ACI-Bench swapped-tag files to test the speaker mapper.
- **Risk:** primary care, not oncology. Treat them as format templates only.

### 4. Hedge lexicon (adopt, small)
- `words/hedges`: MIT, 162 words and phrases (`data.txt`). `dhanauer/hedge-phrases`: 382 hedge phrases from clinical
  documents (Hanauer et al. AMIA 2012). It has no licence file and asks to be cited, so cite it and use it internally only.
  `hedging-lrec/resources`: categorised hedge, booster and discourse-marker lists from spoken discussion. No licence
  file, so treat it as a reference.
- Loughran-McDonald (sraf.nd.edu, updated Mar 2026) has uncertainty, weak-modal and strong-modal lists built partly
  from earnings calls. Its terms: **free for academic research, commercial licence on request**. Fine for the hackathon
  build. For the product story, say we would license it or replace it.
- **Use:** count hedge and booster cues per transcript turn as an `evidence_quality` hint ("anecdotal", "I think", "we
  may be seeing"). Score it on dev; expect a change under the ±0.02 noise floor.

### 5. Text-only speaker-role heuristics (maybe → adopt if transcripts have names)
- No open, offline, text-only role tagger turned up. Usable patterns:
  - mostlyright `role_parser` docs (licence unknown; design only). Use operator/moderator hand-off announcements ("our
    next question comes from X from Firm") and self-identification. Fuzzy-match names against a participant roster.
    Mark unanchored turns as advisory, not as a role.
  - `JS12540/concall-parser` (MIT, pushed 2025-12): speaker detection from capitalised line-start + colon, checked by
    frequency. Moderator cues split prepared remarks from Q&A.
  - Zolensky et al. 2025 (medRxiv, PMC12632672, CC BY-NC-ND): BERT on **linguistic signals alone reaches 82%
    accuracy/F1** for clinical speaker roles. It is method evidence only; no model is released.
- **Use:** in our transcript parser: `Name (Title, Org):` → role lexicon (oncologist/MSL/payer/regulator…). Then
  self-ID regexes ("as a medical oncologist", "I'm a patient", "from NICE"). Then the roster. Otherwise `unknown`.

## Pitch-ready facts (each needs a primary-source check before it goes on a slide)

1. **Regulatory hook.** ICH E2D(R1) (EMA/CHMP/ICH/59123/2024, §2.8 and §4.3.2) names MAH social/digital listening and
   sentiment analysis as an ODCS. The reporting clock starts when a reviewer identifies an AE meeting the four minimum
   criteria. [ema.europa.eu E2D(R1) Step 5 PDF] FDA presented the same E2D(R1) section [fda.gov/media/177715].
   EU: GVP Module VI Rev 2 §VI.B.1.1.4.
2. **Manual triage is the bottleneck.** Pierce et al. 2017 (Drug Saf, PMC5362648): 935,246 Facebook/Twitter posts →
   98,252 classifier-flagged "proto-AEs" → 13 posts sent to causality review, after **three months** of manual curation.
3. **AE mentions are rare and noisy.** WEB-RADR Twitter benchmark (Dietrich et al. 2020, PMC7165158): 1,056 of 57,473
   product tweets (**1.8%**) described a personal AE. French forums (Karapetiantz et al. 2024, PMC11220433): **6.02%**
   of 2,081,296 posts had a normalised drug–ADE pair.
4. **Social data adds value.** Scoping review of 60 studies (Golder et al. 2024, JMIR, PMC11415724): 40% found
   new/unexpected AEs and 15% found AEs earlier than spontaneous reporting. Limit: serious AEs were rarely seen.
   Freifeld et al. 2014 (PMC4013443): Twitter vs FAERS by organ class, Spearman ρ = 0.75.
5. **Compliance blocks cloud LLMs.** ZoomRx survey of 200+ life-sciences professionals: **65% of the top 20 pharmas
   have banned ChatGPT**, mainly over data-leak concerns (FiercePharma, 2024-04-19). Japan clinical-development survey
   (Takata et al., JSCDM, 2025): ~97% rated data security/privacy a major barrier to generative AI.
6. **Market.** AI in pharmacovigilance: USD 0.98B (2026) → 2.70B (2031), 22.5% CAGR. Signal detection is the fastest
   segment (24.5% CAGR). Cloud was 71% of deployment in 2025, which leaves on-prem as the contrarian slot (Mordor
   Intelligence). Research and Markets (GlobeNewswire 2026-10-27): AI drug-safety platforms $2.14B (2025) → $5.39B
   (2030). **Caution:** definitions vary widely. Another R&M release puts "PV software" at only $235M (2026). Quote a
   single source with its definition.
7. Vendor claim (weak; label it as such): an IQVIA case study reports 200 valid AEs from 1.6M social and market-research
   records, and 109 potential AEs in 22,856 CRM call notes.

## Full candidate table

| Candidate | Theme | Form | License / DUA (verified how) | Size / last activity | Benchmark | Verdict |
|---|---|---|---|---|---|---|
| PsyTAR | D1/D2 | c | CC BY 4.0, no DUA (paper + HF tag) | 6,009 sents; 2019 | KF-BERT 72.5 F1 NER (Wegner 2025) | **adopt** |
| ICH E2D(R1) + GVP VI | D5 | a/b | public guidance | 2024 step 5 | n/a | **adopt** (demo/pitch) |
| ACI-Bench | D6/D3 | c | CC BY 4.0 (README) | 207 convs; push 2026-01 | MEDIQA-CHAT 2023 | **adopt** (format) |
| PriMock57 | D6 | c | CC BY 4.0 (LICENSE.md) | 57 consults; 2022 | note-gen benchmark | **adopt** (format) |
| Fareez 2022 simulated interviews | D6 | c | CC BY 4.0 (paper/figshare); HF repack gated | 272 interviews | n/a | maybe (figshare copy) |
| words/hedges | D4 | b | MIT (GH API) | 162 entries; 2022 | n/a | **adopt** |
| dhanauer/hedge-phrases | D4 | b | no licence file; cite | 382 phrases; 2022 | AMIA 2012 | adopt (internal, cite) |
| hedging-lrec/resources | D4 | b | no licence file | lists; 2020 | LREC | maybe (reference) |
| Loughran-McDonald | D4 | b | academic free; commercial licence needed (sraf.nd.edu) | updated 2026-03 | finance std | maybe (hackathon only) |
| BioScope (bigbio) | D4 | c | CC BY 2.0 (HF tag) | biomedical | hedge-cue std | maybe (abstract text, not spoken) |
| ChrisLiewJY/BERTweet-Hedge | D4 | d | MIT (HF tag) | ~135M; 2023 | card: acc 0.968 (unverified) | maybe |
| PeterZhizhin/BERTUncertaintyDetection | D4 | d | no licence (GH API) | 2020 | — | reject (no licence) |
| mostlyright role_parser | D3 | a | unknown; design only | — | — | maybe (pattern) |
| JS12540/concall-parser | D3 | a/b | MIT (GH API) | push 2025-12 | Nifty-200 coverage claim | maybe (heuristics) |
| Zolensky 2025 SRI | D3 | a | CC BY-NC-ND paper; no model | 2025 | 82% acc text-only | info (pitch/method) |
| smart-turn / vogent-turn / pyannote | D3 | d | permissive | audio | — | reject (audio; our input is text) |
| t2t-ner-ade-balanced / t2t-assert-ade-balanced | D1 | d | MIT (HF tag) | T5-base ~220M; 2022 | SMM4H22 strict F1 0.398 / F1 0.655 (README) | maybe (weak; LLM likely as good) |
| scheun/biobert-ade-classifier | D1 | d | Apache-2.0 (HF tag) | 110M; 2026-06 | card: wF1 0.96 ADE-v2 (case reports, unverified) | maybe |
| yseop/SMM4H2024_Task1_roberta | D1 | d | AFL-3.0 | 125M; 2024 | F1-NER 47.2 | reject (weak) |
| MultiTask-T5_AE | D1 | d | MIT (GH API) | 2021 | AE extraction strict F1 0.713 | maybe (no released weights checked) |
| CADEC | D1 | c | CSIRO Data Licence; AskaPatient data "research purposes only" (CSIRO DAP) | 1,250 posts | BERT ~72–86 F1 | maybe (research-only; no DUA signature) |
| ADE corpus v2 | D1 | c | licence unknown (HF card) | case reports | — | maybe (licence unknown) |
| SMM4H 2024/2025 data | D1 | c | registration + DUA on some tasks; Twitter ToS | — | — | **reject (DUA)** |
| n2c2 2018 / MIMIC | D1 | c | DUA + training | — | — | **reject (DUA)** |
| Druglib.com (UCI 461) | D2 | c | research-only, no commercial use, no redistribution (UCI page) | 4.1k reviews | Gräßer 2018 | maybe (dev-only experiments; never ship) |
| Drugs.com (UCI 462) | D2 | c | same terms as 461 (extract failed; assumed) | 215k reviews | — | maybe (same caveat) |
| ATEdrug (PLOS One 2026) | D2 | c | dataset "publicly available"; licence not checked | 3 conditions | — | maybe (check) |
| Arctic-ABSA | D2 | d | weights/licence not confirmed (arXiv abstract) | 395M enc | SemEval14 SOTA claim | maybe (unverified) |
| DOS corpus | D2 | c | Spanish | 877 opinions | — | reject (Spanish) |
| MedDialog / covid_qa_ucsd | D6 | c | site copyright; ToS forbids scraping (HF card) | 260k | — | **reject (licence)** |
| ReMeDi | D6 | c | MIT | Chinese | — | reject (language) |
| ade-extract-3b-v1 | D1 | d | non-commercial (Tavily; not re-checked) | 3B | — | reject |
| vigipy | D5 | d | MIT (GH API), push 2026-10 | Python | PRR/ROR/BCPNN/GPS + longitudinal | maybe (trend report; needs background counts we lack) |
| faerscope-opencore | D5 | a | README says Apache-2.0; GH API no licence | TS | `detectSpikes` rolling z-score | maybe (copy the spike idea) |
| signal-scope (Rust) | D5 | — | not checked | offline FAERS | — | info |
| WALDO | D1 | d | README MIT; GH API none | RoBERTa | 99.66% acc (cannabis) | reject (domain, unverified) |
| CHyMer | D1/D5 | — | data not shared; SNOMED restricted | 2022 | — | reject |
| Algo-Pharma | D5 | — | uses cloud LLMs | — | — | info (shows the 4-gate AE idea: drug, symptom, negative sentiment, negation) |

Takeaway for the trend report: disproportionality (PRR/ROR) needs background counts that our items lack. The cheap,
honest version is the `detectSpikes` idea: a weekly count of safety-negative items per product, a rolling mean, and a
z-score above 2 flagged "spike". That needs no new dependency.

## Themes that came back thin

- **D3 speaker roles (text-only):** no open, offline model. The Tavily report filled the gap with audio turn detectors
  and an invented tagger. Use heuristics (pick 5).
- **D2 English aspect sentiment with a usable licence:** druglib and drugs.com are non-commercial with no redistribution.
  PsyTAR is the only clean English option with separate efficacy and ADR labels.
- **D4 hedge models:** only lexicons are clean. Models are small and tweet- or abstract-trained, with missing licences.
- **D5 open listening-to-trend pipelines:** almost all open code is FAERS disproportionality, not aggregation of
  listening data.
- No Tavily Research pro run, per plan. 11 of the 15 allowed Exa searches were used instead.

## Spend

| Tool | Calls | Cost | Bucket |
|---|---|---|---|
| Tavily Research mini | 2 | unknown (4–110 credits each; OAuth login, so `/usage` was not read) | C |
| Tavily search basic | 4 | 4 credits | D |
| Tavily extract basic | 12 URLs, 10 OK | 2 credits | D |
| Exa MCP search | 11 | ~$0.077 (est.) | ad-hoc |
| Exa MCP fetch | 3 pages | ~$0.003 (est.) | ad-hoc |
| GitHub + HF API | 23 | free | none |

All within the caps (Research 2/2, search 4/4, extract 2/≤10 credits, Exa 11/15 searches + 3/10 fetches).
**R1 check:** 17 saved queries checked against `item_id`, `source_id`, `url` and `title` of all 480 rows in
`test_inputs.jsonl` + `test_inputs.full.jsonl`: 0 hits. **R6:** no dataset adopted into training yet. PsyTAR and any
mock-transcript source must go through the dedupe before use.
