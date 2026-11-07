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

### Composite
The leaderboard score: the plain average of seven parts covering signal type, actionable, which aspects are filled, polarity, speaker, span overlap, and whether spans are verbatim.

### Matched aspect
An aspect that both the gold label and the prediction fill for the same item. Polarity, speaker and span are scored only over matched aspects, so a missed aspect costs far less than a wrong one.

### QWK cliff
The scorer behaviour where polarity agreement reads as perfect when every matched aspect has the same polarity, then collapses to zero as soon as one gold label differs. It is a large tail risk for any system whose matched aspects all share one polarity.
