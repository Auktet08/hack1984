# Signal-to-Dose: the startup

> Launches fail in public before they fail officially. We help launch teams see it coming, and we read their
> private expert conversations without the data ever leaving their building.

**Status: DRAFT, Sat 2026-11-07 evening.** This replaces the startup section of `PROBLEM.md` (§7) as the plan for the
pitch. **Late-evening revision:** the competition theme is privacy-first startups, so the pitch now follows Within3's
business model but puts the AI on the customer's own hardware (§10). The private transcript is the main demo. The
mobocertinib comparison drops to one optional slide. The ideas behind it, and the ones we rejected, are in
`../docs/ideation/2026-11-07-startup-pitch-ideation.html` (ideas 1, 3 and 4 combined; idea 5 is now one optional slide). The working name still needs a
name-conflict search before it goes on a slide.

---

## 1. The pitch (one paragraph)

**Signal-to-Dose** gives pharma launch teams what insights platforms like Within3 give them, privacy-first: the AI
runs on the company's own hardware, and nothing leaves the building. Launch teams learn the most from private
conversations: advisory boards, medical science liaison notes, market research interviews and patient support calls.
That's also the content they can least afford to leak, and two-thirds of the top 20 pharmas have banned or restricted
ChatGPT. A small model on the customer's own laptop reads those conversations with the network off. It labels each
one: what kind of signal it is, whether the team should act, and how it judges the drug on efficacy, safety,
convenience, cost and evidence quality. Every label carries an exact quote, and any side-effect mention is flagged
for the safety team with an audit trail. On the public side, Tavily and Exa gather a drug's news, papers, regulator
decisions and press releases in an afternoon, and the same local model labels them, so private and public views line
up row by row. Customers pay an annual licence per brand and run it on-prem. Setting up a new drug is a search job,
not a consulting project.

**The close (25 seconds, last line of the demo):**
> "Within3 built where pharma hears from its experts. We built a way to read those conversations without them ever
> leaving the building. We'd love to bring that to Within3's customers together."

**Two rules for whoever presents:**
- The demo transcript is a **real but public** meeting (the FDA's poziotinib advisory committee). Say that we process it
  *as if* it were private.
- Talk about Within3 with respect: we follow its model, we don't replace it (§10). Never say Within3 sends data to
  cloud AI. We don't know how its AI is hosted.
- A partnership is something we **want**, not something we have. Say "we'd love to" or "we'd like to". Don't say
  "partner", "integration" or "built with Within3", and don't put their logo on a slide: it reads as an endorsement.
- "Launches fail in public first" is only a **hypothesis**. Use it only if the optional mobocertinib slide shows it
  (§7, S5).

---

## 2. The problem

A launch team has two weekly questions: what happened that we should act on, and how is the conversation moving? The
answers come from two places.

**The public record:** trial results, regulator and payer decisions, papers, news, press releases. There's a lot of
it, and a dip in sentiment means nothing without a baseline. Is a wave of rash complaints in month 6 normal for this
kind of drug, or the start of a problem?

**Private conversations,** where doctors and patients say what they actually think, often months before it's
published:

| Private source | What it is |
|---|---|
| **Advisory boards** | The company pays a small group of leading doctors (often 8–12 oncologists) to spend a few hours discussing the drug. They run under confidentiality agreements, and unpublished data is often shown. |
| **Medical science liaison (MSL) notes** | The company's scientific staff visit doctors one on one and write up what was said in an internal system. |
| **Market research interviews** | Agencies interview doctors, nurses and patients for the company. Recordings and transcripts come back to the brand team. |
| **Patient support calls** | The phone lines and nurse programs that help patients start and stay on the drug. Patients describe side effects and cost problems in their own words. |

Platforms like Within3 already collect these conversations and analyze them with AI on a hosted platform (§10). The
gap we fill is that the AI never leaves the company's own hardware: confidential content, unpublished data and
side-effect mentions stay inside, and every label points to its exact quote.

---

## 3. How it works

```
 PUBLIC (network on)                                   PRIVATE (network off, customer's laptop)
 ─────────────────────────────────────────            ─────────────────────────────────────────
 Tavily + Exa gather the public record                 Advisory-board transcripts, MSL notes,
 for the drug and for analog launches                  market research, patient support calls
            │                                                        │
            ▼                                                        ▼
 Local model labels each item ──────────── same labels ───── Local model labels each turn
 (signal, actionable, 5 aspects,                              (and flags side-effect mentions
  polarity, speaker, exact quote)                              for the safety team)
            │                                                        │
            ▼                                                        ▼
 Trend vs analog launches:  "your safety            Gap map: what experts said in private
 sentiment is tracking mobocertinib's"  ──►         next to what the public record shows,
 Questions for the next advisory board              each side backed by quotes
```

1. **Set up a drug (Tavily + Exa).** Type a drug name. Search builds a small pack: the drug's names, its trials, its
   rivals, the regulators and payers, and a dated event timeline, each with its source URL. It also gathers the
   drug's public items and those of 2–3 analog launches.
2. **Label locally.** The same small model (Qwen3.5-2B, at most 3B parameters) labels everything: signal type,
   actionable yes/no, and five aspects (efficacy, safety, convenience, access/cost, evidence quality). Each aspect gets
   a polarity from −2 to +2, a speaker role and a quote copied exactly from the text. Rules handle the structured
   sources first, and the model fills the gaps.
3. **Compare to analogs.** Plot each aspect's sentiment month by month against the analog launches, with key events
   marked (approval, EU application pulled, failed trial, withdrawal).
4. **Ask the experts.** When an aspect drifts toward the failure pattern, or the public record says nothing about it
   (for example, convenience), the product suggests questions for the next advisory board, each citing the public
   quote that prompted it.
5. **Read the answers privately.** The transcript is labeled on the same laptop with the network off, in the same
   schema, so public and private views line up row by row. Any side-effect mention gets a safety-triage flag, with the
   four reporting criteria each pointing at its quote.

---

## 4. Why privacy is the point

- **The content can't leave the building.** Private talks contain unpublished data, launch strategy, doctors' names
  and patients' health details. A cloud AI service puts that on someone else's servers. A 2024 ZoomRx survey of 200+
  life-sciences staff found 65% of the top 20 pharmas had banned ChatGPT, mostly over leaks of sensitive data (Fierce
  Pharma, April 2024, checked 2026-11-07). Endpoints reported it as "restrict", so the slide says "banned or
  restricted".
- **Side-effect mentions create a legal duty, and screening for them is mandatory work.** This is the strongest
  privacy-first argument we have, and the way into an account (§8).
  - ICH E2D(R1), final since Sep 2025, says companies should regularly screen digital platforms under their
    responsibility for adverse events. Per report D, the reporting clock starts when a reviewer identifies a case
    that meets the four minimum criteria.
  - EPHMRA's guidelines (2025) say agencies running company-commissioned market research must report **any** adverse
    event, serious or not. Amgen's supplier contract asks vendors to catch reportable events from all sources.
  - Today people read every transcript and note line by line. Pierce 2017 (report D, not re-checked): 935,246 posts
    gave 13 cases for review after three months of manual work.
  - Side-effect text holds patients' health details, and the company is legally responsible for it. Our flag checks
    the four criteria, points every box at its exact quote, and logs the reviewer's decision as an audit trail, all on
    the customer's hardware.
  - Always say "triage candidate", never "reportable". A person makes every decision, and the 2B's recall is
    unmeasured.
- **It avoids a long IT approval.** A new cloud vendor touching confidential data needs security and legal reviews.
  Software that runs offline on the company's own hardware is an easier yes.
- **It's cheap at volume.** Once installed, a local model costs close to nothing per item. We will measure cost per 100
  items on the Mac (lean plan item 8).
- **It runs with the network off,** which is how the judges test us.

---

## 5. Why Tavily and Exa

They aren't a bolt-on. They're how the company scales.

| Job | Tool | Why this tool |
|---|---|---|
| Gather a drug's public record, by date | **Exa** search API with date filters; **Tavily** news search with date bounds | Exa takes a description of the page you want and returns full text with dates. Tavily is strong on dated news and regulator pages. |
| Build the drug pack (names, trials, rivals, bodies, timeline) | **Exa** (structured runs) + **Tavily** search | Every entry keeps its source URL, so the UI shows where background facts came from. |
| Find analog launches and their history | **Exa** find-similar + date-filtered search | "Pages like this one" finds comparable launches without a hand-made list. |
| Find public expert-meeting transcripts | **Exa** search, then a direct fetch from fda.gov | How we found the poziotinib transcript (§6). |
| Live mode in the demo | **Tavily** search → local labeling | Shows a fresh public item labeled by the local model. |

**Hard line:** web search only ever touches the public side. Queries use generic public terms (drug, trial, outcome),
never a customer's confidential wording and never hackathon test items. Every call is logged in
`research/ledger.jsonl`. Search is never called in the scored, network-off run.

---

## 6. Evidence so far (Sat 2026-11-07)

| What | Result | Where |
|---|---|---|
| Probe harvest, mobocertinib vs poziotinib | 13 Exa searches, **$0.091** total. Mobocertinib: 48 dated items naming the drug. Poziotinib: 40. No overlap with the test set. | `out/startup/probe_items.jsonl`, ledger |
| Early-warning sign for mobocertinib | **July 2022:** Takeda pulled its EU application after European regulators asked for more data, **15 months before** the US withdrawal (FiercePharma, 2022-07-28). Side-effect management papers kept appearing through 2022–23. | probe items |
| Gap in the mobocertinib record | Coverage clumps at approval (16 items) and withdrawal (17), with only ~15 items in the 18 months between. The full harvest must search quarter by quarter. | probe items |
| Real expert-meeting transcript | The FDA's verbatim transcript of the poziotinib advisory committee, 22 Sept 2022: 205 pages, ~40,000 words, 30+ named speakers (FDA reviewers, panel oncologists, Spectrum, patients). It mentions mobocertinib 10 times and amivantamab twice. | `research/raw/odac-2022-09-22-poziotinib/` |
| Public labels for Tagrisso and Rybrevant | Rules-only labels exist for all 1,733 unlabeled items, but they're skewed: almost all aspects come from FDA adverse-event reports (negative by construction). There are zero convenience or access/cost labels. | `out/labels/unlabeled.jsonl` |

**Labeled with the Gemini stand-in (Sat late evening, `src/startup/label.py`, `PROBLEM.md` decision 9):**

| What | Result | Where |
|---|---|---|
| Transcript turns (S3 done) | 241 speaker turns → 345 rows (long turns cut at about 200 words). Roles come from the roster and self-introductions. 226 rows labeled (15+ words, not introductions). No failures, every quote verbatim. | `out/startup/poziotinib_odac_turns.jsonl`, `out/startup/labels/odac.jsonl` |
| **Gap view data** | Mean polarity by speaker group. **Efficacy:** FDA −1.2 (n=15), committee +0.1, Spectrum +1.2, public hearing +1.3. **Safety:** FDA −1.3, committee −0.6, Spectrum +0.5, public +0.5. **Evidence quality:** FDA −1.1, committee −1.0. **Access/cost:** no mentions. That's a clear split between regulators and patients, plus a gap ready for "what to ask your experts". | `out/startup/labels/odac.jsonl` |
| **Side-effect demo pair** | The caregiver turn `ODAC22-T151-2` gets safety +1 ("simple solutions work ed to counteract the side effects"), and its text names diarrhea, paronychia and rash. So item 6's rules fill the side-effect quote box from the turn text, not from the aspect quote. | `out/startup/labels/odac.jsonl` |
| **Mobocertinib, no curve** | Only 1–4 items per quarter in 2022–23. Efficacy stayed at about +1 every quarter until Q4 2023 (−1.8, the trial failure). The EU pull (2022-07-28) is labeled an **actionable regulatory signal**. The S5 slide: "Sentiment didn't warn. The signal type did, 15 months early." | `out/startup/labels/probe.jsonl` |

**Why two analog drugs.** Mobocertinib had a real launch that failed, and it was Rybrevant's direct rival, so it
gives us the curve. Poziotinib never launched, but its advisory committee meeting is public and verbatim, so it gives us
the transcript.

---

## 7. How we execute it this weekend (deadline Sun 2026-11-08, 11:00 EST)

Everything here depends on the local model path (lean plan item 3), which North owns. The startup work is mostly
harvesting and UI, so it can run in parallel. Owners other than North are proposed, because `PROBLEM.md` §10 roles
aren't agreed yet.

| # | Work | Output | Owner (proposed) | Effort |
|---|---|---|---|---|
| S1 | **Full mobocertinib harvest.** Quarterly date windows 2021–2024, about 25 Exa searches (~$0.20) plus a few Tavily news searches to fill the 2022–23 gap. Dedupe against test. | `out/startup/mobocertinib_items.jsonl` | T2 or T3 | ~1 h |
| S2 | **Mobocertinib pack.** Names (mobocertinib, Exkivity, TAK-788), trials (EXCLAIM, EXCLAIM-2), rivals (amivantamab, poziotinib), dated timeline (approval, EU pull, EXCLAIM-2 result, withdrawal), each with a URL. | `out/startup/mobocertinib_pack.json` | T2 or T3 | ~1 h |
| S3 | ✅ **Done** (`src/startup/transcript_turns.py`). **Clean the transcript into turns.** Strip line numbers and page headers, fix split words, and output `{speaker, role, text}` per turn. Roles come from self-introductions. | `out/startup/poziotinib_odac_turns.jsonl` | North (feeds the transcript path) | ~1 h |
| S4 | 🟡 **Stand-in labels done** for the transcript and probe items (Gemini, `src/startup/label.py`), so S5 and S6 can start now. Rerun with `--backend local` when the 2B lands. **Smoke test first:** run the 2B on about 20 transcript turns. Every reply must parse as JSON, use only real clause IDs, and give labels a person would agree with on a quick read. If it fails, the demo uses rules-labeled public items plus the transcript, and nothing runs overnight. **Then label everything** with the local model: the mobocertinib items, the transcript turns, and the news, PubMed and press items for Tagrisso and Rybrevant. | label files under `out/startup/` | North (Mac, overnight) | overnight |
| S5 | **Optional: one mobocertinib slide.** The default is a dated event timeline (approval Sep 2021, EU application pulled Jul 2022, EXCLAIM-2 missed its endpoint and US withdrawal announced Oct 2023), with each event labeled by our schema. The EU pull shows as an actionable regulatory signal 15 months early. Draw a sentiment curve only if S1 finds about 5+ non-neutral items per quarter. The probe found just 16 items across Jan 2022–Sep 2023. The withdrawal came from a failed trial, with no new safety signal, so a sentiment dip may never appear. | One slide | T3 | ~1 h |
| S6 | **Gap view and suggested questions.** Flag aspects that are thin (few or no public items, e.g. convenience) or split across speakers (excluding FDA adverse-event items). Turn each into a template question citing the public quote. Show the transcript's labels side by side. | Analyze / gap screen | T2 (UI), North (rules) | ~3 h |
| S7 | **Pitch.** The §1 paragraph cut to a 25-second close, plus 3–4 slides. Every number checked against its primary source (report D rule: no unsourced numbers). | slides | T3 | ~1 h |

**Order:** S3 and S1 first (they feed S4 overnight), then S2, S5, S6 and S7 on Sunday morning.

**Demo flow (fits `PROBLEM.md` §8):**
1. Air-gap: network off, load the poziotinib meeting transcript, and show labeled turns, the safety flag and the gap
   view, all from the local model. For the safety flag, show the pair: the caregiver in the open public hearing ("my
   wife Bobbi… diarrhea… rash", positive in tone) fires all four boxes, and an FDA reviewer's trial statistic doesn't.
   Point out that a sentiment tool would score the caregiver positive and miss the case.
2. Feed: a Tagrisso/Rybrevant signal card, clicked through to its quote.
3. Live: network on, Tavily pulls a fresh public item, and the local model labels it.
4. Optional: the mobocertinib slide (S5).
5. Close: the 25-second line in §1, then the "Built to plug into Within3" slide (§8).

**Cut lines if we run out of time:** drop S5 first, then S6's suggested questions (keep the side-by-side), then S2 and
S1. Never drop the safety-net submission (lean plan item 1).

---

## 8. How it works as a company (after the hackathon)

| Part | Plan |
|---|---|
| **Buyer** | Brand and launch teams, medical affairs and market access at mid-size and large pharma, starting with oncology launches. |
| **Way in** | The safety team. Side-effect triage on private listening is something companies must do, and the audit trail (quote, source, time, model version, reviewer decision) is a compliance product in its own right. Once safety trusts it, the insight product sells into the same account. |
| **Tiers** | *Public Pulse:* public record and analog comparison (Tavily + Exa). *Private Signals:* advisory boards, MSL notes and interviews labeled offline. *Launch Room:* weekly brief, alerts and export. |
| **Pricing** | Annual licence per brand, deployed on-prem or in the customer's private cloud. A laptop tier (2B model) and a server tier (larger model, same pipeline). |
| **Partner fit** | We follow Within3's model (insights from advisory boards, field teams and the public record, turned into launch decisions) and add one thing: the AI runs inside the customer's walls. We'd like to offer it to Within3's customers together (slide below and §10). If that doesn't happen, it stands as a product on its own. |
| **What compounds** | The analog library (every launch processed makes the baseline better), the launch-signal label scheme, per-therapeutic-area tuning, and the provenance and compliance layer. |
| **Roadmap** | Analog bands once there's enough history per launch; live advisory-board copilot (labels turns as they're spoken); customer-owned fine-tuning from reviewer corrections (cut for this weekend). |

**Slide: "Built to plug into Within3"** (shown after the close; text only, no Within3 logo)
- **Private tier:** Within3 customers whose policies keep confidential content off hosted AI run our labeler on their
  own hardware, in the same workflow.
- **Same schema, both sides:** advisory-board turns and public items get the same labels, so they can feed a view like
  Within3's Launch Intelligence™.
- **First step:** a pilot on one advisory-board export, run on the customer's laptop with the network off.

Why it's credible: Within3 already works with outside partners. Dataverse (Feb 2026) is an invite-only partner network
built around its platform. Those partners supply data rather than AI, so don't claim more than that. And we found no
on-prem option in Within3's public offering (§10).

---

## 9. Risks and open questions

- **The hypothesis probably won't hold**, which is why it's now an optional slide. Mobocertinib failed on a
  confirmatory trial, not a sentiment drift, and the public record between approval and withdrawal is thin.
- **Within3 sells "Launch Intelligence™".** Don't use that phrase as our product description.
- **The analog data is thin.** Dozens of articles per launch, not thousands. Use monthly or quarterly points and say
  how many items sit behind each one.
- **The 2B's labels on news and transcripts aren't measured yet.** Show quotes next to every score so judges can check.
- **The gap demo is staged.** The transcript is real but public, and the question set is templated.
- **Pitching to the sponsor.** Frame it as a layer on top of an insights platform, not a replacement.
- **Unverified slide facts.** The ChatGPT-ban figure, ICH E2D wording and market sizes all need a primary-source check
  (report D lists them).
- **The Exa key is in the chat transcript.** Rotate it after the hackathon. It lives in `~/.config/exa/key`, outside
  the repo.

---

## 10. Within3: the model we follow, and where we differ

Researched Sat 2026-11-07 with web search, using only Within3's own pages and press coverage. These were not
Tavily/Exa calls, so they aren't in the ledger. Treat everything below as Within3's own claims.

**What Within3 does:**

| Product | What it is | Source |
|---|---|---|
| **Virtual advisory boards** | Asynchronous online advisory boards. It claims "the world's top 20 pharmaceutical companies count on" them. An **AI Moderator Assistant** "summarizes discussions as they happen" and suggests prompts. | within3.com/virtual-advisory-boards |
| **Insights management** (since 2021) | Collects insights from field teams (MSLs) and HCPs across the product lifecycle. A 2023 update claimed AI cuts analysis and reporting work by up to 90%. | Within3 press release, Aug 2023 |
| **Launch Intelligence™, powered by Know Everything™** (Sep 2025) | "Life-science trained AI" that combines customer data with Within3's own data into one real-time market view: field activity, HCP engagement, social listening (including competitor intelligence) and claims data. | Business Wire, 2025-09-08; within3.com |
| **Dataverse** (Feb 2026) | An invite-only partner network that adds real-world data (EHR, claims, specialty data) to Launch Intelligence. | Business Wire, 2026-02-18 |

**Is it local?** As far as public information shows, **no**. Within3 looks like a hosted platform.
- Its privacy policy says data may be processed "in the United States and other locations around the world" and
  refers to unnamed "third-party vendors".
- It shows a SOC audit badge and claims "total security and compliance".
- We found no on-prem or offline option. Within3 doesn't publicly say which AI models it uses or where they run.

So the honest claim is "we found no on-prem option", **not** "Within3 sends your data to cloud AI".

**Where we differ:**

| | Within3 (public claims) | Signal-to-Dose |
|---|---|---|
| Where the AI runs | Hosted platform (no on-prem option found) | Customer's laptop or server, network off |
| Who sees confidential content | The vendor and its subprocessors | Nobody outside the company |
| Evidence for each insight | AI summaries | An exact quote behind every label (citation validity 1.0 by construction) |
| Side-effect mentions | Not mentioned on the product pages we read | Safety-triage flag with an audit trail |
| Scope | Full platform: data network, consulting, recruiting experts | One narrow piece: labeling, run locally |

**How to say it on stage:** "Within3 showed that launch teams run on insights from experts. We asked what that
looks like when the AI never leaves the building." Present it as a privacy-first version of their model, or a
private tier their customers could ask for, not as a replacement.

**People:**
- **CEO: Erin Mistry**, appointed in June 2026 (Business Wire, 2026-06-22). She was previously Chief Commercial
  Officer at CorMedix, where she led the DefenCath launch. Before that she held roles at Syneos Health, MedImmune and
  AstraZeneca. Within3 says she has launched 20+ assets across eight therapeutic areas, and she sits on the Pharma AI
  Council.
- **CTO: Jason Smith.**

**Opening line for her:** "We followed your model and asked what it looks like fully on-prem. Would that be useful to
your customers as a private option?"

**Questions worth asking her** (good for networking, and they test our premise):
1. Do customers ask for on-prem or private-AI options for advisory-board content?
2. How do you handle side-effect mentions that come up in advisory boards?
3. Would a local labeler be useful to you as an add-on, or does it compete with Know Everything?
