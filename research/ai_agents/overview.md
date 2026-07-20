# AI Agents and the Scientific Method - Relevance Map

## Purpose of This Document

This document serves as the bridge between the classical scientific method and
the AI-agent literature. It identifies which components of the scientific method
are most directly applicable when building or evaluating AI agents that reason
scientifically, then maps each to the specific documents in this research hub
that cover it in depth.

---

## The Six High-Priority Areas

Reading across the classical loop, the philosophy of science literature, and the
current AI agent research frontier, six areas are most actionable for AI agents
attempting to apply the scientific method rigorously.

---

### Area 1 - Hypothesis Generation and Falsifiability

**Why it's the most critical area**:
The hypothesis is the atomic unit of scientific reasoning. An agent that
generates vague, unfalsifiable, or trivially true hypotheses cannot do science
regardless of how sophisticated its downstream machinery is. Popper's
falsificationism is not just philosophy here - it is an architectural
requirement. A well-formed AI agent hypothesis must specify what observation
would disconfirm it.

**What makes it hard for AI agents**:
- LLMs trained on literature have strong priors toward confirmation (modus
  ponens patterns in training data). They are systematically weaker at
  generating disconfirmatory tests.
- Generating a novel hypothesis is indistinguishable from confabulation without
  external grounding. The model cannot tell the difference.
- "Novel" and "correct" are orthogonal axes that LLMs conflate.

**Research frontier**: The POPPER framework (arXiv:2502.09858) directly
addresses this by structuring agents around falsification rather than
confirmation. See `hypothesis_generation.md`.

---

### Area 2 - Causal Reasoning (vs. Correlation)

**Why it's critical**:
Science's core goal is identifying causal mechanisms, not statistical
associations. An AI agent that outputs "A correlates with B" has described
the data. An agent that outputs "A causes B via mechanism M, controlling for
confounders C₁…Cₙ" has done science. The distinction is not trivial.

**What makes it hard for AI agents**:
- LLMs exhibit a documented "disjunctive bias" - they can infer "A OR B causes
  C" reliably, but systematically fail at conjunctive causation ("A AND B
  together cause C"). This mirrors human adult reasoning biases.
- Causal direction is asymmetric; statistical association is symmetric. LLMs
  default to symmetric thinking.
- The interventional logic of causation (Pearl's do-calculus) is not naturally
  representable in the autoregressive generation paradigm.

**Research frontier**: Active inference architectures, IRIS, Causal-Copilot,
and SciExplorer. See `causal_reasoning.md`.

---

### Area 3 - Experimental Design and Active Learning

**Why it's critical**:
Good science is not passive observation - it is designed intervention. Choosing
which experiment to run next, under resource constraints, is a decision problem
that Bayesian active learning formalizes. An AI agent doing science without
principled experiment selection wastes resources and introduces sampling bias.

**What makes it hard for AI agents**:
- The space of possible experiments is combinatorially large. Exhaustive search
  is impossible.
- The agent must balance exploitation (testing the most likely hypothesis) with
  exploration (testing surprising predictions that could overthrow the paradigm).
- Multi-step experimental designs require long-horizon planning and uncertainty
  tracking across time.

**Research frontier**: LAPD, GO-CBED, GRACE, Sequential Bayesian Experimental
Design. See `bayesian_experiments.md`.

---

### Area 4 - Self-Evaluation, Verification, and Epistemic Calibration

**Why it's critical**:
An agent that cannot assess the reliability of its own outputs cannot be trusted
as a scientific reasoner. Confidence calibration - knowing how certain to be - 
is a prerequisite for rational scientific updating. An overconfident agent
overstates findings; an underconfident agent discards real signals.

**What makes it hard for AI agents**:
- LLMs are systematically miscalibrated: confident about wrong answers, uncertain
  about correct ones, in domain-dependent patterns.
- Self-verification requires a different cognitive operation than generation.
  LLMs are weak at verification relative to generation - an asymmetry that
  mirrors the broader challenge in science.
- Physics-constrained models reduce calibration error by ~37%, suggesting domain
  structure can anchor calibration.

**Research frontier**: POPPER's Type-I error control, self-consistency sampling,
conformal calibration, rubric-guided verification. See `calibration.md`.

---

### Area 5 - Multi-Agent Architecture (Generator, Critic, Validator)

**Why it's critical**:
Science is a social epistemic enterprise. Peer review, replication, and
adversarial debate are not optional features - they are structural mechanisms
that science evolved to compensate for individual cognitive limitations and
conflicts of interest. AI agents doing science in isolation suffer the same
problems as lone researchers with no peer review.

**What makes it hard for AI agents**:
- A single LLM acting as both generator and critic draws from the same
  parametric well. It cannot genuinely disagree with itself.
- Multi-agent debate requires genuine diversity of "beliefs" - not persona
  switching within one model.
- Critic agents need ground truth anchoring to be useful rather than
  sycophantic.

**Research frontier**: EvoScientist, AI Co-Scientist, Indibator, BioDisco.
See `multi_agent_review.md`.

---

### Area 6 - Epistemic Provenance and Accountability

**Why it's critical**:
Scientific knowledge is only as trustworthy as the chain of evidence and
reasoning behind it. When AI agents generate findings, the epistemic provenance
problem emerges: who is responsible for the claim, what evidence grounded it,
and how can it be audited? Without provenance, AI-generated science cannot be
replicated, challenged, or corrected.

**What makes it hard for AI agents**:
- LLMs do not cite sources in the mechanical sense - they pattern-match against
  training data without maintaining explicit pointers to grounding documents.
- Citation accuracy in current AI research systems ranges from 40–80%
  (DeepTRACE, 2025). Most AI-generated scientific text contains unsupported
  statements indistinguishable from supported ones.
- No global standard for AI disclosure in research yet exists (expected 2026).

**Research frontier**: Research Object paradigm, DeepReviewer 2.0, DeepTRACE,
International Science Council global standards initiative.
See `provenance.md`.

---

## Relevance Map

| Scientific method component | Most relevant for AI agents? | Priority | Document |
|---|---|---|---|
| Falsifiable hypothesis generation | Yes - architectural requirement | Critical | `08` |
| Causal vs. correlational reasoning | Yes - core scientific task | Critical | `09` |
| Experimental design / active learning | Yes - resource allocation | Critical | `10` |
| Self-evaluation and calibration | Yes - trust and reliability | Critical | `11` |
| Multi-agent peer review | Yes - social epistemology for AI | High | `12` |
| Epistemic provenance and accountability | Yes - reproducibility and trust | High | `13` |
| Statistical inference (p-values / Bayesian) | Partially | Medium | `04` |
| Replication and robustness | Yes - AI outputs need replication norms | Medium | `03`, `06` |
| Paradigm shifts (Kuhn) | Conceptually useful, not directly operational | Low | `02` |
| Incommensurability (AI vs. human) | Emerging problem | Low | `06` |

---

## The Core Structural Challenge

All six areas share a common root problem:

> **LLMs are trained to predict the next token given prior tokens, optimized
> against human-generated corpora. Scientific reasoning is not the same as
> mimicking human scientific writing.** The distributional average of scientific
> text is not the same as correct scientific reasoning. Every area above is, at
> its core, an attempt to escape the distributional average and approach genuine
> epistemic process.

The three structural interventions most likely to close this gap:

1. **Grounding in external data and reality** (active learning, wet lab loops,
   real-time experimental feedback - not just literature)
2. **Adversarial verification** (separate critic agents, Type-I error control,
   falsification-first architectures)
3. **Explicit uncertainty representation** (Bayesian frameworks, calibration,
   conformal guarantees - not just softmax probabilities)

---

## Key Sources

- arXiv:2502.09858 (2025). POPPER: Automated hypothesis validation.
- arXiv:2506.21329 (2025). Active inference AI systems for scientific discovery.
- arXiv:2602.07594 (2026). Learning to self-verify.
- arXiv:2603.08127 (2026). EvoScientist.
- arXiv:2502.18864 (2025). AI Co-Scientist (Google Research).
- arXiv:2604.11261 (2026). Inspectable AI for Science.
- arXiv:2509.13365 (2025). The Provenance Problem.
- IJCAI (2025). Toward Reliable Scientific Hypothesis Generation.
- International Science Council (2026). AI Disclosure in Research.
  https://council.science/our-work/ai-disclosure-in-research/
