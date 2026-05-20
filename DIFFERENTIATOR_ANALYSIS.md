# Differentiator analysis — what makes this gym sellable vs existing benchmarks

**Author:** Dhiren · **Last updated:** 2026-05-20 · **Branch:** `feat/pixel-agent-fork`

The action item Ankit gave on the 5/20 call:

> *"Look into the difference between DOM and pixel, when we should use one, what is SOTA and pros and cons of each? What could be our differentiator?"*
>
> *"Have more samples with understanding of where the model is breaking and where it's not."*

This doc is the answer. Three sections:
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

> *"My hunch is, pixel-based gym will help in training. Ideally most of the models are a combination of both. Like where they can use DOM parser they will use it. Where they can use pixel based, that could be a fallback."* — Ankit, 5/20

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

**Why it wins:** Ankit explicitly asked about this on the original interview (*"if you are putting browser click button at somewhere else where it's not very configurable, not viewable"*). No major benchmark does it systematically. Exposes the dependency on `data-test-id` selectors vs visual recognition.

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

**Why it wins:** Genuinely novel — no benchmark in the survey does this. Catches a class of failures other benchmarks miss. Directly answers Ankit's *"they are not using multimodal verifiers, we are using multimodal verifiers"* line from the call.

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

## The combined story for CVPR / Ankit

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

## Open questions for Ankit

1. **For CVPR demo: which of the 3 differentiators to lead with?** My recommendation: #1 (failure-mode indexing) as the lead because it's the business pitch; #2 and #3 as the research depth.
2. **Multi-model rerun budget?** To make the comparison robust, we should run Claude Sonnet 4.5, 4.6, and at least one open-source baseline. Estimated $50-100 in API.
3. **Is "we made a benchmark" enough, or do we need a "we benchmarked SOTA models and here's where they fail" narrative?** The latter is much stronger but needs more API runs.
