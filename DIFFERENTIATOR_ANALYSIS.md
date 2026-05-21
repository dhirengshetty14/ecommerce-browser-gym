# Differentiator analysis — what makes this gym sellable vs existing benchmarks

**Author:** Dhiren · **Last updated:** 2026-05-20 · **Branch:** `feat/pixel-agent-fork`

1. **DOM vs Pixel: SOTA + pros/cons** (research roundup)
2. **Feature matrix vs existing benchmarks** (where the gaps are)
3. **12 candidate differentiators ranked + top 3 picks**

---

## 1. DOM vs Pixel: state of the art

### What every major browser-agent system uses for observation

| System | Observation modality | Action space | Source |
|---|---|---|---|
| **Anthropic Computer Use** | Pure pixel screenshots | (x, y) mouse + keyboard | [docs](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool) |
| **OpenAI Operator (CUA)** | Pure pixel screenshots | (x, y) mouse + keyboard | [announcement](https://openai.com/index/computer-using-agent/) |
| **WebVoyager** (CMU 2024) | Screenshot + SoM marks from DOM walk | Click by mark ID | [arxiv 2401.13919](https://arxiv.org/abs/2401.13919) |
| **SeeAct** (OSU 2024) | Screenshot + raw HTML (hybrid) | Element attrs / textual choices | [arxiv 2401.01614](https://arxiv.org/abs/2401.01614) |
| **VisualWebArena** (CMU 2024) | Tests all 4 modalities | Element ID or AX node | [arxiv 2401.13649](https://arxiv.org/abs/2401.13649) |
| **Browser-Use** (OSS) | Accessibility tree + optional screenshot | Element-index click `@e5` | [github](https://github.com/browser-use/browser-use) |
| **UI-TARS / OS-Atlas / ShowUI** | Pure pixel only | Normalized pixel coords | [arxiv 2501.12326](https://arxiv.org/abs/2501.12326) |

### Reported success rates (anchor your hypotheses against these)

| Benchmark | Best pure-pixel | Best DOM/AX | Human |
|---|---|---|---|
| WebVoyager (e-commerce web tasks) | 93.9% (UI-TARS, heavy GUI fine-tune) | 59.1% (GPT-4V + SoM) | ~85% |
| VisualWebArena Shopping | ~25% (GPT-4o + SoM, no fine-tune) | ~15% (AX-tree text only) | 88.4% |
| WebArena (sandboxed real apps) | n/a | 30–40% (Sonnet, no fine-tune) | ~78% |
| τ-bench retail (text-only) | n/a | 50% pass@1 / 6% pass^8 (GPT-4) | ~95% |

### Pros / cons

| Approach | Pros | Cons | Train models for | Realistic deployment |
|---|---|---|---|---|
| **DOM / accessibility tree** | Cheap (~5K tokens/step). Deterministic. Stable selectors. RL-training-friendly (low variance). | Requires semantic markup on the page. Doesn't generalize to apps without ARIA/test-id. Doesn't capture visual hierarchy. | Tool calling, structured-output reasoning, retrieval-augmented agents | Apps you control + apps with public APIs |
| **Pure pixel** | Most general — works on any UI. Captures visual cues (layout, color, animation). Matches Claude Computer Use's training distribution. | Expensive (~1500 tokens/screenshot). Slow. Coordinate accuracy is the bottleneck without GUI fine-tuning. | Multimodal vision-language, 2D spatial reasoning, GUI fine-tuning | Unknown / arbitrary UIs |
| **SoM (pixel + AX-tree marks)** | Best success at fixed VLM. Discretizes grounding (mark IDs, not coordinates). Image is still the primary signal. | Requires AX tree access. Mark numbering is unstable across turns. Higher token cost than DOM. | Same as pixel + benefits from discrete-action training | Apps with reasonable ARIA roles (~90% of production web) |
| **Hybrid DOM + pixel** | Best of both — DOM where available, pixel as fallback. Closest to how Anthropic Computer Use actually works internally. | More complex implementation. Two pipelines to maintain. Comparison metrics harder to interpret. | Production-realistic agents | All deployments |

### When to use what — recommendation matrix

| Goal | Best modality | Why |
|---|---|---|
| Train a tool-calling model (SFT/RL) | DOM | Cheap, fast, deterministic reward signal |
| Train a multi-modal GUI agent | Pixel / SoM | Forces the model to read visual layout |
| Benchmark a frontier LLM "out of the box" | SoM | Strongest at fixed VLM; closest to deployment-realistic |
| Production deployment on a known app | Hybrid (DOM primary) | Cheap and reliable when DOM is available |
| Production deployment on unknown apps | Pixel | Only modality that works without markup |

### The economic case for both

> *"My hunch is, pixel-based gym will help in training. Ideally most of the models are a combination of both. Like where they can use DOM parser they will use it. Where they can use pixel based, that could be a fallback."* 


This is the right framing. The pragmatic conclusion:

- **Pixel approach** trains the visual-grounding capability (the bottleneck that limits Claude Computer Use's success rate)
- **DOM approach** trains the planning capability cheaply, then transfers to pixel deployment
- **A gym that supports BOTH with the same verifier** is uniquely valuable — you can study which observation modality each model variant benefits from, train ablations, generate failure data per modality, etc.

We already have this.

---

## 2. Feature matrix — where we sit vs the existing benchmarks

| Feature | WebArena | VisualWebArena | WorkArena | τ-bench | Mind2Web | WebShop | **YOUR GYM** |
|---|---|---|---|---|---|---|---|
| Real browser (not text-sim) | ✓ | ✓ | ✓ | ✗ | ✗ | partial | ✓ |
| **Per-step rewards (dense)** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| **Categorical failure-mode labels** | ✗ | ✗ | ✗ | partial | ✗ | ✗ | **✓** |
| pass^k consistency metric | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ |
| **Multi-modal verifier** (screenshot + state) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **opportunity** |
| **DOM + pixel side-by-side under same verifier** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **opportunity** |
| **Same-task UI variation benchmark** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **opportunity** |
| Policy documents grounding | ✗ | ✗ | partial | ✓ | ✗ | ✗ | opportunity |
| Hallucination metric | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | opportunity |
| **Cost-per-success reporting** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **opportunity** |
| **Hidden-affordance taxonomy** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **✓ (already!)** |
| RLVR-ready verifier API | ✗ | ✗ | ✗ | ✓ | ✗ | partial | ✓ |
| Frontier-LLM success rate | 30-40% | 20-25% | 20-30% | 50%/6% | <30% | high | TBD |

The interesting cells: **bolded** ones where we either are unique or have a clear opportunity.

---

## 3. 12 candidate differentiators ranked

Scored on **novelty** (research/PR value) / **effort** (engineering cost) / **$ value** (Deccan business pitch).

| # | Differentiator | Novelty | Effort | $ Value | Total |
|---|---|---|---|---|---|
| 1 | **Failure-category-indexed trajectory store** | 🔥🔥🔥 | 🟢 low | 🔥🔥🔥 | **🎯 BEST** |
| 2 | **Same-task UI-variant robustness benchmark** | 🔥🔥🔥 | 🟡 med | 🔥🔥 | 🎯 strong |
| 3 | **Multi-modal verifier (screenshot + state)** | 🔥🔥🔥 | 🟡 med | 🔥🔥 | 🎯 strong |
| 4 | **Hidden-affordance taxonomy** | 🔥🔥 | 🟢 low | 🔥🔥 | strong |
| 5 | **DOM vs Pixel head-to-head under same verifier** | 🔥🔥🔥 | done | 🔥 | strong |
| 6 | **Cost-per-success as first-class metric** | 🔥🔥 | 🟢 low | 🔥🔥 | medium-high |
| 7 | **Reward-density spectrum study** | 🔥🔥🔥 | 🟡 med | 🔥 | medium |
| 8 | **Policy-document-grounded UI tasks** | 🔥🔥 | 🟡 med | 🔥 | medium |
| 9 | **URL/product-ID hallucination metric** | 🔥🔥 | 🟢 low | 🔥 | medium |
| 10 | **Taxonomy-vs-search navigation A/B** | 🔥 | 🟢 low | 🔥 | medium |
| 11 | **Task-brief paraphrasing robustness** | 🔥 | 🟢 low | 🔥 | low-medium |
| 12 | **Long-horizon multi-task chaining (10+ sub-flows)** | 🔥 | 🔴 high | 🔥 | low |

---

## Top 3 picks — paper-worthy framings

### 🏆 #1 — Failure-category-indexed trajectory store

**The pitch (one sentence):**
> "The first browser-agent benchmark where every failed trajectory carries a categorical label, enabling targeted training-data slicing by failure mode."

**Why it wins:** matches Deccan's core business pitch directly — selling failure-mode-specific training data. Infrastructure is already built (`failure_category` field on every milestone; `primary_failure_category` returned by every verifier evaluation). The differentiator is a thin query layer + a publication.

**Customer pitch:** *"You need 1,000 trajectories where the agent applied a category-restricted promo to the wrong line? Query our store. You need 500 trajectories where the agent picked the wrong product variant from a 5-option dropdown? Same answer."*

**Work to ship:**
- Run all 12 tasks × seeds 0-4 on multiple agents → ~250 trajectories
- Build `scripts/query_trajectories.py` — filter JSONLs by `failure_category`, `score range`, `task_id`, etc.
- Write 1-page DATA_PRODUCT.md describing the slice queries supported
- Total: ~1 day

**Paper-worthy framing:**
> "Most browser-agent benchmarks report aggregate success rate. We propose **failure-mode-indexed trajectory generation**, where every episode carries one of 16 categorical failure labels (`wrong_variant`, `picked_distractor_product`, `discount_applied_to_wrong_line`, `wrong_subscription_setup`, etc.). This enables (a) targeted training-data generation for specific failure modes and (b) fine-grained analysis of agent capabilities beyond binary success/fail."

---

### 🏆 #2 — Same-task UI-variant robustness benchmark

**The pitch:**
> "The first benchmark that measures robustness to UI variation by holding the task constant and varying ONLY the rendered UI."

**Concrete design:**
For each of 5 representative tasks (A1, A3, B2, C1, C2), generate 5 UI variants of the same underlying task:

| Variant | What changes |
|---|---|
| `baseline` | Original gym UI |
| `cta_below_fold` | Critical CTA pushed below the 800px viewport (must scroll) |
| `hidden_in_dropdown` | Critical button moved into a `<details>` or hover menu |
| `renamed_labels` | "Add to Cart" → "Buy Now", "Submit" → "Confirm" |
| `micro_buttons` | Critical button has 50% smaller bounding box |

Run all agents on all 25 (task × variant) combinations. **Variance in success rate IS the robustness score.**

**Work to ship:**
- Build a UI-variant generator (Jinja template branching on `?variant=` query param)
- Add 5 variant strings to each of the 5 chosen tasks
- Extend `eval/compare.py` to iterate task × variant
- Write up the variance results
- Total: ~2 days

**Paper-worthy framing:**
> "We introduce **UI-Variant Robustness (UVR)**, a metric for measuring browser-agent dependence on specific UI affordances. For each task we generate K UI variants that preserve task semantics but vary visual placement, naming, and visibility. Agent robustness is the success-rate stability across variants. We find frontier LLMs degrade by ΔX% when CTAs move below the fold and ΔY% when buttons shrink below 40px width."

---

### 🏆 #3 — Multi-modal verifier (screenshot + state)

**The pitch:**
> "Most browser-agent verifiers check final database state. We add a verifier that ALSO inspects the rendered screenshot — catching UI-state divergence and rendering bugs invisible to state-only checks."



**Concrete design:**
Add a new `VisualMilestone` type alongside `Milestone`:

```python
@dataclass
class VisualMilestone:
    name: str
    weight: float
    # Predicate: takes final screenshot path, returns bool.
    # Implementation: send to Claude vision with a yes/no prompt.
    check_visual: Callable[[Path], bool]
    failure_category: str
```

Example: a "Gift wrap visually shown on cart line" verifier sends Claude the final-cart screenshot with the prompt *"Is there a gift-wrap indicator visible on any line item in this cart? Answer 'yes' or 'no'."* If state says `gift_wrap=true` but the UI didn't render it, the multi-modal verifier catches the bug that the state-only verifier missed.

**Work to ship:**
- Add `VisualMilestone` dataclass to `verifiers.py`
- Implement a `_visual_check` helper that calls Claude vision with image + prompt
- Add 2-3 visual milestones to existing tasks where they apply (C2 gift wrap, C4 gift message, A4 cart total visible)
- Write up methodology
- Total: ~2 days, plus API budget

**Paper-worthy framing:**
> "We propose **multi-modal verifiers** that grade both the final database state AND the rendered screenshot. This catches a distinct class of failures—UI/state divergence and rendering bugs—that pure state-based verifiers miss. On task C2 split-shipping, we identify K cases where the state-based verifier reports success but the user-visible cart page is inconsistent with what was stored. Our multi-modal verifier correctly fails these."

---


A 3-bullet pitch slide:

```
ShopGym: a browser-agent benchmark with three novel contributions

1. FAILURE-MODE-INDEXED TRAJECTORIES — 16 categorical labels per
   episode; queryable training-data slices by failure type.
   (Direct Deccan business pitch.)

2. UI-VARIANT ROBUSTNESS METRIC — same task × 5 UI variants;
   measure success-rate variance instead of just aggregate success.

3. MULTI-MODAL VERIFIERS — verify the screenshot AS WELL AS the
   state, catching UI-state divergence other benchmarks miss.

Same gym scored by the same verifier under DOM, pixel/SoM, and
hybrid observation modalities — direct apples-to-apples comparison
across modalities at a fixed VLM.
```

---

## Recommended sequencing

Given the CVPR deadline (~10-14 days):

| Day | Task |
|---|---|
| Day 1 (today) | Verifier audit ✓ (this commit). Differentiator analysis ✓ (this doc). |
| Day 2 | Differentiator #1 (trajectory query layer): write `scripts/query_trajectories.py` + generate 250 trajectories on the 12-task matrix |
| Day 3-4 | Differentiator #2 (UI-variant benchmark): variant generator + 5×5 matrix runs |
| Day 5-6 | Differentiator #3 (multi-modal verifier): `VisualMilestone` + 3 example milestones |
| Day 7 | Pull it all together — paper-style write-up with results |
| Day 8-10 | Polish + demo prep |

---

## Where to look in the codebase

| Differentiator | Files involved |
|---|---|
| #1 Failure-category indexing | `server/verifiers.py` (already has `failure_category`); add `scripts/query_trajectories.py` |
| #2 UI-variant benchmark | `ui/pages/*.html` (Jinja branching); `server/main.py` (variant query param); `eval/compare.py` (matrix expansion) |
| #3 Multi-modal verifier | `server/verifiers.py` (new `VisualMilestone` class); new helper `server/visual_verify.py` |

---

## Open questions

1. **For CVPR demo: which of the 3 differentiators to lead with?** Recommendation: #1 (failure-mode indexing) as the lead because it's the business pitch; #2 and #3 as the research depth.
2. **Multi-model rerun budget?** To make the comparison robust, run Claude Sonnet 4.5, 4.6, and at least one open-source baseline. Estimated $50-100 in API.
3. **Is "we made a benchmark" enough, or do we need a "we benchmarked SOTA models and here's where they fail" narrative?** The latter is much stronger but needs more API runs.

---

# Update — Deeper SOTA survey (2024-2026) + stronger differentiators

Comprehensive read of what the frontier is actually shipping in 2024-2026,
followed by 6 new differentiator candidates that go beyond the original 12.

## 1. Complete SOTA model + benchmark inventory

### Production frontier systems (commercial)

| System | Released | Observation | Action | Training | Best benchmark | Source |
|---|---|---|---|---|---|---|
| **Anthropic Computer Use** (claude-3.5/4/4.5/4.6) | Oct 2024 → current | Pure pixel screenshot | (x,y) mouse + keyboard | Post-training for computer-use | WebVoyager-like ~56% out-of-the-box; higher in production | [docs](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool) |
| **OpenAI Operator / CUA** | Jan 2025 | Pure pixel screenshot | (x,y) mouse + keyboard | GPT-4o-based, RL post-trained | Reportedly ~50% on web tasks | [announcement](https://openai.com/index/computer-using-agent/) |
| **Google Gemini Computer Use / Project Mariner** | preview 2024-2025 | Pixel + accessibility tree (hybrid) | Element clicks + keyboard | Gemini 2.x post-trained | Not publicly benchmarked | google blog posts |
| **Manus.AI** | early 2025 (viral) | Hybrid (closed) | Closed | Multi-model orchestration | Self-reported strong on WebVoyager-style tasks | manus.im |
| **Browser-Use** (OSS) | 2024 → current | Accessibility tree + optional screenshot | Element index `@e5` | Wraps frontier LLMs (no fine-tune) | ~70% reported on internal evals | [github](https://github.com/browser-use/browser-use) |

### GUI-specialized vision-language models (the "fine-tune" track)

| Model | Year | Observation | Action | Params | WebVoyager / equivalent |
|---|---|---|---|---|---|
| **UI-TARS** (ByteDance) | 2024 | Pure pixel | Normalized (x,y) | 7B / 72B | ~85% (7B), ~94% (1.5 release 2025) |
| **OS-Atlas** (HKUST) | 2024 | Pure pixel | Normalized (x,y) | 4B / 7B | ~60% WebVoyager equivalent |
| **ShowUI** (ShowLab) | 2024 | Pure pixel | (x,y) | 2B | ~75% on ScreenSpot |
| **CogAgent** (Tsinghua/Zhipu) | 2023-2024 | Pixel + caption | Element-based | 18B | Strong on Mind2Web |
| **SeeClick** (HKUST/Salesforce) | 2024 | Pure pixel | (x,y) | 9.6B | First grounding-focused model |
| **AutoWebGLM** (Tsinghua) | 2024 | DOM-augmented | DOM-based actions | ChatGLM-based | Strong WebArena |

### Benchmarks (the targets these systems get scored on)

| Benchmark | Modality enforced | Task count | Best human | Best model |
|---|---|---|---|---|
| **WebArena** (CMU 2023) | DOM / AX-tree | 812 | ~78% | ~40% (Sonnet 3.5) |
| **VisualWebArena** (CMU 2024) | Pixel + AX-tree | 910 | ~88% | ~25-30% (GPT-4o + SoM) |
| **WorkArena** (ServiceNow 2024) | Both | 33-150 (L1-L3) | not measured | ~30% L2 |
| **τ-bench** (Sierra 2024) | Tool-only (no UI) | 165 (airline+retail) | ~95% | ~50% pass@1, ~6% pass^8 |
| **Mind2Web** (OSU 2023) | DOM | 2,350 | n/a | ~40% step accuracy |
| **Online-Mind2Web** (2024) | Both (live web) | 300 | not measured | ~25% |
| **WebVoyager** (Tsinghua 2024) | Pixel + SoM | 643 | ~85% | ~94% (UI-TARS-1.5) |
| **WebShop** (Princeton 2022) | Text-DOM | 12K instructions | ~89% | ~50% top |
| **OSWorld** (HKU 2024) | Pure pixel | 369 | not measured | ~12% (best in 2024) |
| **AgentBench** (Tsinghua 2023) | Multiple | 1,376 | not measured | ~40% best |
| **BrowserGym** (ServiceNow 2024) | Framework, not benchmark | — | — | — |

## 2. The 5 trends from this survey

### Trend 1 — Pure pixel is winning AT FRONTIER

The two largest commercial deployments (Anthropic Computer Use, OpenAI Operator)
both ship **pure-pixel** as the primary modality. They were trained explicitly
for coordinate-based grounding. UI-TARS-1.5 hitting ~94% on WebVoyager with pure
pixel proves the ceiling is high enough for production.

### Trend 2 — But "at fixed model" (zero-shot frontier LLM), SoM wins

The published VisualWebArena Shopping numbers (~25% with GPT-4o + SoM vs ~15%
with AX-text alone) show that **without GUI fine-tuning**, marks-derived-from-
accessibility-tree beats both pure coordinates and AX-text-only. This is what
WebVoyager, SeeAct, and VisualWebArena all converged to.

### Trend 3 — DOM-only is increasingly research-only

Browser-Use (the OSS leader) and WebArena are the last holdouts of pure-DOM.
Production has moved on. DOM is now considered "training data for the planning
component" while pixel is "training data for the grounding component."

### Trend 4 — Hybrid is the production architecture

Anthropic and Google internally use both — DOM/AX-tree where available
(faster, cheaper), pixel as fallback (general, robust). Manus.AI does the same.
Hybrid is what real-world agents look like.

### Trend 5 — Benchmarks haven't caught up

Every benchmark in the table above enforces ONE modality. There is **no
benchmark that grades all four (DOM / pixel / SoM / hybrid) under the same
verifier on the same tasks.** This is a methodological gap with research value.

## 3. Pros / cons updated for 2026

| Approach | Token cost / step | Wall time / step | At fixed Sonnet 4.6 | With GUI fine-tune | Real-world deployment |
|---|---|---|---|---|---|
| **Pure DOM/AX-text** | ~1-3K tokens | ~1s | ~30-40% WebArena | n/a (no GUI VLM uses pure DOM) | Apps you control |
| **SoM (pixel + AX marks)** | ~2-4K tokens | ~2-3s | ~25-60% WebVoyager | rarely used | Most public-web apps |
| **Pure pixel** | ~1.5-3K tokens | ~3-5s | ~20-50% | ~94% (UI-TARS-1.5) | Universal — only modality that works on apps without semantic markup |
| **Hybrid (DOM-primary, pixel fallback)** | ~2-4K tokens | ~2-4s | ~40-60% (estimated) | n/a | Production-realistic |

## 4. Which one for THIS gym?

The strongest answer for a **benchmark-and-trajectory-data company**:

**Support all four. Compare them head-to-head under the same verifier.**

This is exactly what the existing branch already does (DOM agent + Pixel/SoM
agent on the same gym with the same verifier). The methodology IS the
differentiator — no other benchmark does this side-by-side comparison cleanly.

**Production recommendation for THIS gym specifically:**

| Use case | Recommended modality | Reasoning |
|---|---|---|
| Generating training data for SFT/RL of frontier models | **DOM agent primary, pixel for variety** | DOM is cheap; you can produce 10K trajectories for the cost of 500 pixel ones |
| Demonstrating the gym to LLM labs (pitch) | **Hybrid demo** | Show both work; show side-by-side comparison; impress with the verifier-agnostic story |
| Stress-testing visual robustness | **Pure pixel** | Required to surface visual-grounding failures |
| Selling failure-mode-labeled trajectories | **All four, queryable by modality** | Customers can buy "1000 DOM-agent failures" or "1000 pixel-agent failures" separately |

## 5. Six STRONGER differentiator candidates (beyond the original 12)

These go beyond what I proposed earlier. Each is informed by gaps the SOTA
survey above revealed.

### 🏆🏆 NEW #1 — Adversarial UI generator

**The pitch:**
> "A closed-loop benchmark where a separate adversary model mutates the UI to
> maximize agent failure rate, producing labeled hard-negative trajectories
> targeted at specific failure modes."

**Why it's the strongest single new angle:**
- **Genuinely novel** — no browser-agent benchmark does this. The closest
  analogues are vision adversarial papers (CleverHans, autoattack) which
  don't transfer directly to UI.
- **Scales automatically** — once the adversary works, you have an infinite
  source of hard training data. This is the "Deccan trajectory factory"
  business model literally automated.
- **Paper-worthy at top venues** — CVPR, NeurIPS, ICML all have track
  records of accepting adversarial training papers.
- **Hard to copy** — even if a competitor reads the paper, training the
  adversary itself is non-trivial.

**Concrete design:**

```
Loop:
  for episode in budget:
      1. Adversary model: given (task, baseline UI, recent agent trajectory),
         propose UI mutation that's most likely to break the agent.
         Mutations: hide a button behind a dropdown, rename a CTA, swap
         button positions, change product names to similar-looking ones,
         introduce a modal, etc.
      2. Apply mutation → run agent → record success/failure + category.
      3. If failed: save trajectory tagged with mutation_type + failure_category.
      4. Adversary trains itself on (mutation_type → failure_rate) signal.
```

The adversary is a frontier LLM with a constrained mutation toolkit. The
output is a continually-growing dataset of "agent failures targeted by
adversarial UI design."

**Work to ship:**
- ~3-5 days
- New file `adversary/mutator.py` — LLM-driven UI mutation generator
- New file `adversary/loop.py` — the closed-loop runner
- Reuses existing failure_category infrastructure
- Output: `trajectories/adversarial/<mutation>__<task>__<id>.jsonl`

**Paper-worthy framing:**
> "We propose **adversarial UI generation**, where a separate LLM-based
> adversary proposes UI mutations that maximize browser-agent failure
> rate. The resulting trajectories are an order of magnitude more
> challenging than the base benchmark and produce a long tail of labeled
> hard-negative training data. This is the first browser-agent benchmark
> with an automated adversarial generation loop."

---

### 🏆 NEW #2 — Cross-modality agreement matrix

**The pitch:**
> "First study to ask: given the SAME task + SAME base model, do DOM, SoM,
> and Pixel agents agree on the action sequence? Where do they diverge?"

**Why strong:**
- Surfaces *modality-induced* failure modes — which failures are due to
  the observation modality vs the model
- Publishable as a methodology paper
- Cheap given the existing infrastructure (DOM + SoM both built)

**Design:**
For each of 12 tasks × seeds 0-4, run DOM agent + SoM agent + Hybrid agent
on the same base model. For each (task, seed) compute:
- **Agreement rate**: fraction of step-N actions that are semantically equivalent
- **Divergence point**: first step where they diverge
- **Divergence outcome**: which modality's choice led to success

This produces a 12×3×3 agreement-confusion matrix per model — a novel
artifact that nobody has published.

**Work to ship:** ~2 days (leverages existing `eval/compare.py`)

---

### 🏆 NEW #3 — Cost-bounded benchmark

**The pitch:**
> "Each task has a TOKEN BUDGET. Success requires completing the task within
> the budget. Cost-per-success becomes the primary metric."

**Why strong:**
- **Production-realistic** — real deployments care about cost per task, not
  unbounded task success
- Forces efficient navigation patterns to emerge
- Punishes infinite-scroll / repeated-retry behaviors that today's
  benchmarks ignore
- Easy add-on to existing infrastructure

**Design:**

| Task tier | Budget |
|---|---|
| Easy (A1, B1) | 5K input tokens, 1K output |
| Medium (A2, B2, C1, C2) | 12K input, 2K output |
| Hard (A3, B3, C3) | 25K input, 5K output |
| Very hard (A4, B4, C4) | 50K input, 10K output |

When the agent exceeds the budget, episode ends with whatever state it's in.
The cost-aware success rate is the primary metric.

**Work to ship:** ~1 day (add budget tracking to `LLMBrowserAgent.run()` loop)

---

### 🏆 NEW #4 — Side-effect detection

**The pitch:**
> "Verifier checks not just 'did the goal happen' but 'did the agent do
> anything else it wasn't supposed to'."

**Why strong:**
- Real production concern (agent adds extra products, applies wrong promo)
- No benchmark currently scores this
- Cheap to add to existing verifiers (just add "forbidden actions" predicates)

**Design:**
Each task suite gains `negative_milestones` — actions the agent must NOT take:
- A1: no other product in cart
- B1: no other address modifications
- C1: no other promo applied; cart subtotal matches expected

**Work to ship:** ~1 day

---

### 🏆 NEW #5 — Recovery from injected failures

**The pitch:**
> "Mid-episode, inject a deterministic UI failure (network error, partial
> page load, modal pop-up). Does the agent recover?"

**Why strong:**
- Tests *agent robustness* explicitly, not just task completion
- Models the real-world reality where UIs are flaky
- Differentiator that no current benchmark has

**Design:**
A "failure injector" middleware in the harness that triggers deterministically
on step N:
- `inject="network_500"` → next page load returns 500 error
- `inject="modal_block"` → modal appears blocking the target element
- `inject="lazy_load_stall"` → critical UI element doesn't render

Task variants: same base task + injection point = "recovery benchmark."

**Work to ship:** ~3 days

---

### 🏆 NEW #6 — Multi-model cross-comparison study (THE pitchable artifact)

**The pitch:**
> "We benchmarked X frontier models on Y tasks across Z modalities and
> categorized N thousand failures into M categorical types. Here's the data."

**Why this is the actual product:**
- It's not a methodology — it's the OUTPUT
- LLM labs care about real numbers more than they care about benchmarks
- Selling the data IS the business
- Generating this is what differentiator #1 (trajectory store) was a prerequisite for

**Models to run:**
- Claude Sonnet 4.5, 4.6 (frontier)
- Claude Haiku 4.5 (cost baseline)
- GPT-4o, GPT-4.1 (competitor)
- Gemini 2.x (third competitor)
- Qwen 2.5-VL 72B (open-source frontier)
- UI-TARS-7B (GUI-specialized open-source)

7 models × 12 tasks × 3 seeds × 2 modalities = **504 episodes** = ~$200-400.
Output is a publishable data report + a sellable trajectory store.

---

## The new strongest pitch

Combine NEW #1 (Adversarial UI generator) + NEW #6 (Multi-model study) +
the original #1 (Failure-category indexing):

> **An adversarial closed-loop browser-agent benchmark where a separate
> LLM mutates UIs to maximize agent failure rate across 7+ frontier
> models in 3 observation modalities, producing a continually-growing
> labeled trajectory store indexed by 16 categorical failure modes —
> directly queryable for targeted training-data generation.**

That's the CVPR / NeurIPS abstract.

That's also the Deccan business pitch: *"give us a failure mode you
care about, we sell you targeted trajectories at scale."*

---

## Updated recommended sequencing (CVPR-aware)

Given the demo deadline:

| Day | Task |
|---|---|
| Done | Verifier audit + oracles + DOM/Pixel infra |
| Day 1 | NEW #1 Adversarial UI mutator prototype (5-10 mutation types) |
| Day 2 | NEW #6 Multi-model harness — wire up GPT-4o + Gemini + Qwen via the same agent interface |
| Day 3 | Run the 7-model × 12-task matrix on baseline (no adversary) — ~$100 |
| Day 4 | Run the same matrix with adversarial UIs — ~$200 |
| Day 5 | Failure-mode taxonomy auto-clustering on the resulting ~500-1000 failed trajectories |
| Day 6 | Write the paper-style report (`docs/PUBLISHABLE_RESULTS.md`) |
| Day 7-10 | Polish, slides, demo |

This gets you the **strongest possible CVPR-ready artifact** in ~10 days.

---

## Top 3 recommended differentiators (final)

After this deeper survey, the three differentiators to ship by CVPR are:

| # | Differentiator | Why |
|---|---|---|
| 🥇 | **Adversarial UI generator + failure-category indexed trajectory store** | Novel, scalable, business-aligned, publishable |
| 🥈 | **Multi-model cross-modality comparison study** | The artifact LLM labs actually want to buy |
| 🥉 | **Multi-modal verifier** | Methodological novelty as a sidecar contribution |

The CVPR pitch: *"We built the first adversarial closed-loop browser-agent
benchmark that produces failure-mode-indexed trajectories across DOM, SoM,
and pixel observation modalities. We benchmarked 7 frontier models and
found [SPECIFIC NUMBERS]. We're now selling the trajectory store."*
