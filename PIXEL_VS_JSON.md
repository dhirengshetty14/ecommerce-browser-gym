# Pixel-based vs DOM-based browser agents — a head-to-head comparison

A controlled experiment inside the ecommerce-browser-gym to answer:
**at a fixed VLM (Claude Sonnet 4.5, no GUI fine-tuning), does a
screenshot-based agent perform as well as a DOM-based agent on real
e-commerce tasks?**

Both agents drive the same Playwright browser through the same 12
tasks, scored by the same observation-agnostic verifier. The only
difference is what they perceive and how they act:

| | **DOM agent** (`agents/llm_agent.py`) | **Pixel agent** (`agents/pixel_agent.py`) |
|---|---|---|
| Observation | JSON list of `[data-test-id]` interactables | Screenshot with Set-of-Mark annotations + URL + manifest |
| Action space | `click(selector)`, `fill(selector, value)`, `select(selector, value)`, `submit(selector)`, `navigate(path)` | `click(mark_id)`, `type_text(mark_id, text)`, `key(name)`, `scroll(direction, amount_px)`, `finish()` — **no navigate** |
| Marks/IDs | gym-provided `data-test-id` attrs | accessibility-tree-derived (deploys to any ARIA-compliant site) |
| Reasoning | tool-use only | tool-use + extended thinking (4000-token budget) + plan-then-act prompt |

---

## Methodology

### Why this specific design

| Design choice | Rationale |
|---|---|
| **Set-of-Mark with accessibility-tree marks** | At a fixed VLM (no GUI fine-tuning), SoM with AX-tree-derived marks beats both raw-coordinate clicking and AX-text-only on browser benchmarks. VisualWebArena Shopping reported SoM 19.3% vs AX-tree-text 15.1% at fixed model. The 93.9% pure-pixel SOTA on WebVoyager (UI-TARS family) requires heavy GUI post-training we can't replicate via API. For a fair, publishable comparison, SoM with AX-tree is the right baseline. |
| **AX-tree marks, NOT `data-test-id`** | The pixel agent must be deployable against any web app, not just this gym. ARIA roles (`button`, `link`, `textbox`, `combobox`, `checkbox`, `tab`, etc.) are present on ~90% of production web. Test-id is our convention; the pixel agent doesn't depend on it. |
| **No `navigate(url)` tool** | Forces pure visual navigation. The agent must reach every page by clicking visible marks — exactly like a human deployed on an unfamiliar site. The DOM agent has `navigate(path)` as a shortcut; this is a deliberate handicap on the pixel agent, mirroring real-world deployment realism. |
| **Extended thinking + plan-then-act** | Multi-turn checkout tasks (especially C4) have 9 milestones and 20+ steps. Reactive single-pass reasoning loses the thread. Plan-then-act forces a persistent revised plan across turns. Extended thinking gives the model 4000 tokens of private reasoning per turn to maintain that plan. |
| **Same verifier for both agents** | The `Probe(state, url, initial_state)` reads only `GymState` — no DOM. Both agents are scored against identical milestone predicates, identical `failure_category` labels, identical weight totals. Score values are directly comparable. This is the headline feature that makes the comparison publishable. |
| **Same model, same seeds** | Both agents run on the same `--model` flag and the same seed list. Differences in score are attributable to observation modality + action space + prompt — NOT to model strength variation. |

### The matrix

- **2 agents**: `llm` (DOM/JSON) + `pixel` (SoM)
- **12 tasks** spanning Discovery / Account / Checkout × {easy, medium, hard, very-hard}
- **3 seeds**: 0, 1, 2 (deterministic task perturbations)
- **1 model**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)

Total: **72 episodes** (plus oracle on the same matrix as a verifier sanity gate, +36 episodes).

### Metrics collected per episode

- `score` (0.0–1.0, weighted milestone sum)
- `success` (bool, all-required-fired AND score ≥ 0.999)
- `steps_taken`
- `tokens_in_total`, `tokens_out_total` → `cost_estimate_usd` at $3/$15 per MTok
- `primary_failure_category` (τ-bench-style categorical label)
- Per-milestone fired/missed map

### Aggregated metrics

For each (agent, task) cell:
- **Mean score** across seeds (and std)
- **Success rate** = fraction of seeds that succeeded
- **pass^k_consistent** = 1 iff all k seeds succeeded (τ-bench-style reliability)
- **Mean steps** to completion (or until max_steps cap)
- **Cost per episode** (USD)

For each agent overall:
- All of the above, aggregated across all 36 episodes (12 tasks × 3 seeds)

Head-to-head DOM vs Pixel:
- **Δ score** per task (pixel mean − DOM mean)
- **Winner** per task (dom / pixel / tie)
- **Cost ratio** = pixel_cost / dom_cost (how much more expensive is pixel?)

### Hypotheses to falsify (recorded BEFORE the data)

These are written down here so the post-hoc analysis can score how
many predictions held:

1. **DOM agent dominates on tightly-named test-id tasks (A1, B1, B3)** — these were authored against specific selectors; the test-ids are basically a cheat-sheet.
2. **Pixel agent narrows the gap on visual-merchandising tasks** — Today's Deals page, category browsing, the home page rails. The annotated screenshot shows what's actually featured; the DOM JSON doesn't capture visual hierarchy.
3. **Pixel agent breaks on multi-input form tasks (B1)** — the address form has 6 inputs. Click-then-type-then-click-then-type is fragile when one input loses focus.
4. **Pixel agent handles our hidden-dropdown edge cases at least as well as DOM** — both must explore behind "More ▾" and `<details>` toggles, but the visual ▼ chevron is unambiguous.
5. **Pixel agent fails variant-selection tasks more often (C1, C4)** — `<select>` dropdowns require click-then-click across two turns, doubling the failure surface.
6. **Cost ratio is 5–10×** (not the 25× wild prediction) — because annotated screenshots are ~1500 tokens but the DOM JSON is also substantial on rich pages.
7. **Pixel agent's pass^3 will lag DOM agent's** — consistency suffers when grounding has more variance.

---

## Results

> **STATUS: scaffolding written, awaiting full matrix run.**
> Run `python -m eval.compare --agents llm,pixel --seeds 0,1,2 --tasks all`
> to generate the numbers. The script writes `_summary.json` +
> `_summary.md` into `trajectories/comparison/`. Paste the markdown
> table content below.

### Overall comparison

<!-- paste table from trajectories/comparison/_summary.md -->

| Agent | Episodes | Success Rate | Mean Score | Mean Steps | Tokens In | Tokens Out | Cost (USD) |
|---|---|---|---|---|---|---|---|
| llm   | _36_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| pixel | _36_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Per-task scores (mean across 3 seeds; ✓ if pass^3, ✗ otherwise)

| Task | DOM agent | Pixel agent |
|---|---|---|
| A1/buy_wireless_mouse     | _TBD_ | _TBD_ |
| A2/filter_laptop          | _TBD_ | _TBD_ |
| A3/configure_bundle       | _TBD_ | _TBD_ |
| A4/home_office_bundle     | _TBD_ | _TBD_ |
| B1/add_address            | _TBD_ | _TBD_ |
| B2/track_and_return       | _TBD_ | _TBD_ |
| B3/account_overhaul       | _TBD_ | _TBD_ |
| B4/subscription_juggle    | _TBD_ | _TBD_ |
| C1/promo_partial          | _TBD_ | _TBD_ |
| C2/split_shipping_gift    | _TBD_ | _TBD_ |
| C3/subscription_loyalty   | _TBD_ | _TBD_ |
| C4/mega_checkout          | _TBD_ | _TBD_ |

### Head-to-head: Δ score and cost ratio

| Task | DOM | Pixel | Δ | Winner | Cost ratio (pixel/dom) |
|---|---|---|---|---|---|
| _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Failure-mode distribution

Which categories dominate for each agent? Use the
`primary_failure_categories` counter from `_summary.json`.

| Failure category | DOM agent | Pixel agent |
|---|---|---|
| _TBD_ | _TBD_ | _TBD_ |

---

## Analysis (post-data)

> Fill in after running the comparison. Suggested structure:

### Which hypotheses held?

Compare the seven predictions above against the data. Score each
True / False / Mixed. **Intellectual-honesty checkpoint** — don't
edit predictions retroactively.

### Where pixel agent wins (if anywhere)

If there's a task category where pixel ≥ DOM despite the extra cost,
that's the strongest case for pixel-based deployment. Specifically
look at visual-merchandising tasks (deals, home rails) and tasks
with hidden visual affordances (collapsed `<details>`, "More ▾"
menus).

### Where pixel agent loses

Most likely: multi-input forms (B1 address), variant selection (C1
T-shirt, C4 mega), and subscription/return-flow tasks that require
clicking deeply nested controls.

### Cost-per-success

The practical deployment metric:
```
cost_per_success = total_cost_usd / count_of_successful_episodes
```
Compare this between agents. Even if pixel agent's success rate is
80% of DOM agent's, if its cost is 5× higher, the cost-per-success is
~6× — meaning DOM agent is **6× more economical** to deploy.

### When is pixel agent worth it anyway?

The pixel agent's headline strength isn't success rate — it's
**deployability**. It works on:
- Apps without `data-test-id` markup (most internal enterprise tools)
- Apps that change frequently and break CSS selectors
- Apps that surface task-critical info in images, not text

For a customer-service-agent deployment against a fixed app like
ShopGym (which our DOM agent was authored for), pixel is strictly
worse. For a deployment that needs to work on a thousand different
e-commerce sites, pixel is the only viable approach.

---

## Limitations + future work

1. **One model only.** Re-run with Claude Sonnet 4.6, Opus, and
   ideally a GUI-fine-tuned model (UI-TARS, ShowUI) to test how much
   of the gap is closeable with better models.
2. **k=3 is a small consistency sample.** k=5 or k=8 would give a
   sharper pass^k signal but at proportional cost.
3. **Same gym both ways.** A real test of pixel deployability would
   point the pixel agent at a real shopify store or external app —
   the AX-tree-based marks should work, but we haven't verified.
4. **Hybrid agent not tested.** A real production agent would use
   DOM where available and fall back to pixel where it isn't.
   That's what Anthropic Computer Use actually does internally.
   Could be a follow-up paper.
5. **Marks max out at 80 per page.** Rich category pages (e.g.
   home with 24+ product cards) may filter out tail elements.
   Configurable but not tuned for this study.

---

## References

- **Set-of-Mark prompting** (Yang et al., 2023): https://arxiv.org/abs/2310.11441
- **WebVoyager** (CMU, 2024): https://arxiv.org/abs/2401.13919
- **SeeAct** (OSU, 2024): https://arxiv.org/abs/2401.01614
- **VisualWebArena** (CMU, 2024): https://arxiv.org/abs/2401.13649
- **Anthropic Computer Use docs**: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool
- **OpenAI CUA / Operator announcement**: https://openai.com/index/computer-using-agent/
- **Browser-Use** (open source): https://github.com/browser-use/browser-use
- **UI-TARS** (ByteDance, 2025): https://arxiv.org/abs/2501.12326

---

## Reproducibility

```bash
# On a fresh clone:
git checkout feat/pixel-agent-fork
pip install -e ".[dev,agent]"
playwright install chromium

# Set the Anthropic key
export ANTHROPIC_API_KEY=...

# Start the gym in one terminal
uvicorn server.main:app --port 8000

# Run the full comparison in another terminal
python -m eval.compare --agents llm,pixel --seeds 0,1,2 --tasks all \
                       --model claude-sonnet-4-5-20250929

# Output:
#   trajectories/comparison/<agent>__<task>__<seed>__<id>.jsonl  (108 files)
#   trajectories/comparison/_summary.json                         (aggregated metrics)
#   trajectories/comparison/_summary.md                           (human table)
```

Wall-clock estimate: 2-4 hours for full matrix.
API cost estimate: $30-50 (Sonnet 4.5, May 2026 pricing).
