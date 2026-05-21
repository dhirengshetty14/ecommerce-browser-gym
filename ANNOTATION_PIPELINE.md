# Annotation pipeline — where AI works, where humans are required

The recurring strategic question: in producing browser-agent trajectory
data, **which pipeline stages can AI do, which need humans, and why?**
This is the blueprint for how the annotation team operates — what to
automate, what to staff with subject-matter experts.

The short version: **AI scales generation; humans guarantee correctness
at the points where being wrong is expensive.** The art is putting the
human exactly where their judgment is load-bearing and nowhere else.

---

## The pipeline, stage by stage

| # | Stage | Who | Why |
|---|---|---|---|
| 1 | Task ideation (what journeys to cover) | **Human-led, AI-assisted** | AI brainstorms breadth; humans pick what's realistic + commercially valuable |
| 2 | Task brief authoring (natural-user phrasing) | **AI drafts, human approves** | AI writes fluent briefs; humans verify the intent is unambiguous and the success criteria are decidable |
| 3 | Adversarial element design (distractors, traps) | **Human** | Requires domain knowledge of *how* agents actually fail; AI tends to make traps too easy or unrealistic |
| 4 | Gym/UI construction | **AI-heavy** | Boilerplate web app; AI writes it fast, humans review for realistic friction |
| 5 | Verifier predicate authoring | **Human-led, AI-assisted** | The verifier IS the ground truth — a wrong verifier poisons every trajectory. Humans must own correctness |
| 6 | Oracle/gold-path authoring | **AI drafts, human verifies** | AI can write the happy path; the oracle scoring 1.0 proves the verifier is right |
| 7 | Trajectory GENERATION (running agents) | **Fully AI** | This is the whole point of the gym — cheap, scalable, deterministic |
| 8 | Per-step reward labeling | **Fully AI (the verifier)** | Deterministic milestone checks; no human in the loop |
| 9 | Failure-mode classification | **AI-first, human-audit** | Rule-based + LLM judge labels at scale; humans spot-check the LLM-judged tail |
| 10 | Tier-1 quality curation | **Human** | Deciding which trajectories are "gold, sellable to a frontier lab" is expert judgment |
| 11 | Edge-case / novel-task labeling | **Human** | When the universal classifier returns `unclassified_failure` and the LLM judge is uncertain |
| 12 | Dataset packaging + provenance | **Fully AI** | Versioning, slicing, manifests — pure tooling |

---

## The dividing line, stated as a principle

> **AI handles everything that is GENERATIVE or DETERMINISTIC.
> Humans handle everything that is JUDGMENT under AMBIGUITY or where
> being wrong is EXPENSIVE and SILENT.**

- **Generative** (AI): writing briefs, building UI, running agents,
  producing trajectories at volume.
- **Deterministic** (AI): per-step rewards, rule-based failure
  classification, packaging. The answer is computable, so compute it.
- **Judgment under ambiguity** (human): is this trap realistic? is this
  brief decidable? is this trajectory tier-1 quality? what failure
  class does this genuinely-novel case belong to?
- **Expensive + silent errors** (human): a wrong verifier predicate
  doesn't crash — it silently mislabels thousands of trajectories. A
  human must own the verifier's correctness.

---

## What this gym already automates (AI, no human needed)

- **Trajectory generation** — `eval/run.py` / `eval/compare.py` run any
  agent across all tasks × seeds, fully unattended.
- **Per-step reward** — the milestone verifier scores every action
  deterministically. Zero human labeling.
- **Failure classification (stage 9)** — `harness/failure_classifier.py`
  labels every failed trajectory from the 38-class universal taxonomy:
  rule-based for ~70% (free, deterministic), LLM judge for the tail
  (`--llm-judge`). A human only audits the LLM-judged subset.
- **Verifier self-validation** — the oracle scoring 1.0 on every task is
  an automated check that the verifier is correct. If an oracle drops
  below 1.0, the verifier (or task) has a bug — caught without a human
  reading trajectories. (This is how we caught the C3 bug.)
- **Dataset slicing/packaging** — `scripts/query_trajectories.py`
  produces failure-mode-indexed slices on demand.

## What still needs a human (and must)

- **Verifier authoring (stage 5).** The single highest-leverage human
  task. A subtly-wrong predicate mislabels everything downstream and
  never throws an error. Humans write + review every verifier; the
  oracle is the safety net.
- **Adversarial design (stage 3).** Knowing that agents fall for
  "Studio Laptop **Pro**" vs "Studio Laptop", or pick the office-category
  monitor, requires having watched agents fail. AI doesn't have that
  prior; it makes traps that are either trivial or unfair.
- **Tier-1 curation (stage 10).** "Is this trajectory good enough to sell
  to a frontier lab as gold SFT data?" is a quality bar only an expert
  can set.
- **Novel-task adjudication (stage 11).** When the rules + LLM judge
  disagree or return `unclassified_failure` on a genuinely new task
  shape, a human assigns the label and (if it recurs) proposes a new
  taxonomy entry.

---

## The annotation-team workflow this implies

For the India annotation team replicating this at scale (300+ tasks):

```
Per task:
  1. [human] propose the journey + adversarial traps   (~30 min)
  2. [AI]    draft the natural-user brief               (instant)
  3. [human] approve brief; confirm it's decidable      (~5 min)
  4. [human] author the verifier milestones             (~30-45 min) ← the load-bearing step
  5. [AI]    draft the oracle gold path                 (instant)
  6. [human] run oracle; if < 1.0, fix verifier/oracle  (~10 min)
  7. [AI]    generate N trajectories across seeds        (unattended)
  8. [AI]    score + classify failures                   (unattended)
  9. [human] spot-audit the LLM-judged failure tail     (~15 min / 100 traj)
 10. [human] tag the tier-1 keepers                      (~10 min)
```

Roughly **~2 hours of expert human time per task**, the rest automated.
The human time concentrates in stages 1, 3, 4 (ideation, traps,
verifier) — exactly the judgment-heavy points. Everything generative or
deterministic is AI. That ratio is what makes a 300-task dataset
economically feasible.

---

## Why this is the operating model Deccan wants

- It puts scarce expert hours only where they change the outcome.
- It makes the per-task cost mostly AI compute, not human labor.
- The verifier-as-ground-truth design means quality is enforced by
  construction (oracle gate), not by exhaustive human review.
- The universal failure taxonomy means the AI classification stage (9)
  generalizes to new tasks, so humans aren't re-labeling from scratch
  each time the catalogue grows.
