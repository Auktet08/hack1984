# Concepts

> Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Labeling and scoring

### Item
One piece of public evidence (an abstract, trial registry record, adverse-event report, label change, regulatory notice, press release or news snippet) about our products, which the system must label.

### Our products
Tagrisso (product A) and the Rybrevant / Lazcluze family (product B). Every judgment in a label is about one of these, never about a rival drug the item happens to discuss.

### Signal type
The single main kind of news an item carries, such as efficacy, safety, regulatory, trial update, competitor move, access/pricing, guideline, expert opinion, or none.

### Actionable
Whether a launch team for one of our products would plausibly change a plan, message or priority because of an item.

### Aspect
One of five dimensions an item may judge a product on: efficacy, safety, convenience, access/cost, and evidence quality. An aspect is left empty unless the text actually judges the product on it.

### Polarity
How positively or negatively an aspect judges our product, on a five-step scale from strongly negative to strongly positive. When unsure between two steps, the milder one is correct.

### Speaker
Who holds the opinion behind an aspect (researcher, clinician, patient, company, regulator, payer or media). For most sources it is fixed by where the item came from; for adverse-event reports it follows the reporter, and for news it follows whoever is quoted.

### Span
The shortest phrase, copied exactly from the item text, that justifies an aspect and its polarity. It never paraphrases and never joins two sentences.

### Gold label
The answer key for an item. For this track most gold labels were drafted by a frontier model and then corrected by reviewer rulings, so matching the drafter's habits matters as much as clinical truth.

### Silver label
A label on an unlabeled item written by the frontier teacher model under the labeling guide, standing in for gold. A silver hold-out is a set of these, sampled to match test's source mix and never used for training or few-shot, that ranks changes dev is too small to tell apart. Silver rewards the teacher's habits, which are close to the gold drafter's but are not ground truth.

### Composite
The leaderboard score: the plain average of seven parts covering signal type, actionable, which aspects are filled, polarity, speaker, span overlap, and whether spans are verbatim.

### Matched aspect
An aspect that both the gold label and the prediction fill for the same item. Polarity, speaker and span are scored only over matched aspects. So an extra aspect that gold leaves empty costs only aspect precision, about as much as a missed one, while a matched aspect with the wrong polarity or a long span also drags down the matched-only parts.

### Oracle run
An upper-bound experiment that replaces chosen fields of a real prediction with gold, to measure how much a perfect version of one lever could add. It bounds only the fields it fills, for example one metric or one source, so its result is that lever's ceiling, never the whole system's.

### QWK cliff
The scorer behaviour where polarity agreement reads as perfect when every matched aspect has the same polarity, then collapses to zero as soon as one gold label differs. It is a large tail risk for any system whose matched aspects all share one polarity.

## Startup demo

### Stand-in label
A label written by a hosted frontier model (Gemini) in place of our local model until the local model is ready, and marked as such on every row so it is never shown as local or network-off output.

### Triage candidate
A speaker turn that names a side effect and meets all four minimum criteria for an individual safety case (a side effect, a suspect product, an identifiable patient, an identifiable reporter), each backed by a quote. It is a prompt for a safety reviewer to decide, never a claim that the case must be reported. A turn that names a side effect but misses a criterion stays visible as an incomplete record.

### Gap view
A grid of how each speaker group at an expert meeting, and the drug's public record, judge one drug on each aspect. An aspect is thin when one side barely mentions it, and split when groups disagree sharply. Each thin or split aspect becomes a suggested question for the next advisory board.
