# AI and the Scientific Method - Closed-Loop Discovery (2025–2026)

## Overview

The most disruptive development in the history of the scientific method since
the invention of the randomized controlled trial is unfolding now: AI systems
that can complete the entire hypothesis → experiment → analysis → publication
cycle with minimal human intervention.

This document covers: what these systems can do, where they are actually
deployed, what remains human-dependent, and what new epistemological problems
they introduce.

---

## The Traditional Bottlenecks AI Is Removing

| Step | Traditional bottleneck | AI intervention |
|---|---|---|
| Literature review | Weeks; human expertise required | Minutes; LLMs can synthesize thousands of papers |
| Hypothesis generation | Human insight + background knowledge | LLMs trained on literature generate novel hypotheses |
| Experimental design | Requires domain expertise | AI agents design protocols; Bayesian optimization guides search |
| Data analysis | Requires statistical + domain expertise | Automated pipelines; natural language to code |
| Paper writing | Days to weeks of human writing | LLMs draft manuscripts from structured results |
| Peer review | Months; expert availability bottleneck | LLMs as first-pass reviewers (augmenting, not replacing) |

---

## Current State of AI-Driven Science (Verified Systems, 2025–2026)

### AlphaFold 2 & 3 (DeepMind, 2020–2024)

The clearest, most consequential existing example. AlphaFold 2 (2020) predicted
the 3D structure of proteins from amino acid sequence with accuracy competitive
with X-ray crystallography. AlphaFold 3 (2024) extended this to DNA, RNA, and
small molecule interactions.

**Impact**: 214 million+ protein structure predictions as of 2024 (Nucleic Acids
Research, 2024), 241M+ as of Sep 2025, and growing. Compressed what would have
been decades of structural biology work. This is AI as a scientific tool within
a human-led research programme, not autonomous science.

Source: Jumper, J., et al. (2021). Highly accurate protein structure prediction
with AlphaFold. *Nature*, 596, 583–589. DOI:10.1038/s41586-021-03819-2

### GNoME (Graph Networks for Materials Exploration, DeepMind, 2023)

Predicted 2.2 million new stable crystal structures (compared to ~20,000
experimentally known). Experimental verification of ~700 novel materials
followed as of 2024.

Source: Merchant, A., et al. (2023). Scaling deep learning for materials
discovery. *Nature*, 624, 80–85. DOI:10.1038/s41586-023-06735-9

### The AI Scientist (Sakana AI, 2024–2025)

The first system to complete the full loop: idea generation → code → experiments
→ results → manuscript → automated peer review. Built on top of frontier LLMs
(GPT-4, Claude) with scaffolding for code execution and literature search.

**Performance (v2, April 2025)**: One of three papers submitted by AI Scientist-v2
to an ICLR 2025 workshop achieved scores exceeding the average human acceptance
threshold - the first instance of a fully AI-generated paper passing peer review.
The experiment was run with ICLR leadership cooperation; reviewers were told some
papers might be AI-generated but not which ones.

**Scope**: Currently limited to machine learning research about machine learning.
The v1 system (arXiv:2408.06292) demonstrated the full pipeline; v2 (April 2025)
was the first to achieve actual peer-review acceptance.

Sources:
- Lu, C., et al. (2024). The AI Scientist v1. arXiv:2408.06292.
- Sakana AI. (2025). The AI Scientist-v2: First AI-generated peer-reviewed paper.
  https://sakana.ai/ai-scientist-first-publication/

### EXPERIGEN (arXiv, 2025)

arXiv:2602.07983. Hypothesis generation framework evaluated against expert human
researchers. Results:
- Generates 2–4× more statistically significant hypotheses than prior methods
- Hypotheses are 7–17% more predictive in out-of-sample testing
- Expert evaluation: **88%** rated moderately or strongly novel; **70%** rated
  as impactful and worth pursuing
- Outperforms single-model baselines and retrieval-augmented generation alone

**Architecture**: Combines structured literature mining, causal reasoning chains,
and multi-round critic feedback.

Source: arXiv:2602.07983 (2025). ExperiGen: Accelerating Social Science Research
via Agentic Hypothesization and Experimentation.

### ResearchEVO (arXiv, April 2026)

arXiv:2604.05587. A two-stage framework for end-to-end automated discovery and
documentation:

**Stage 1 - Evolution Phase**: LLM-guided undirected experimentation. Explores
the solution space without a fixed hypothesis, guided by novelty and
interpretability signals.

**Stage 2 - Writing Phase**: Autonomously generates publication-ready papers
grounded in existing literature, with proper citation and contextualization.

**Novel discoveries**: Discovered previously unproposed algorithmic mechanisms in:
- Quantum Error Correction
- Physics-Informed Neural Networks

Human curation still required for data validation and hyperparameter settings.

Source: arXiv:2604.05587 (April 2026).

### SciDER (arXiv, March 2026)

arXiv:2603.01421. Scientific Data-centric End-to-end Researcher. Unlike other
systems that start from the literature, SciDER starts from *raw experimental
data*.

**Architecture**:
- Four specialized agents: Ideation Agent (hypothesis generation and experimental
  planning), Data Analysis Agent (data cleaning, structuring, analysis reports),
  Experimentation Agent (code development and execution), Critic Agent (result
  evaluation, hypothesis feasibility and novelty validation)
- Self-evolving memory: agents update their knowledge base from each experiment
- Critic-led feedback loops: the Critic Agent evaluates output quality and
  directs revision

**Advantage over general-purpose LLMs**: In empirical benchmarks, outperforms
GPT-4 and Claude in data-grounded hypothesis generation because it grounds
reasoning in the actual data structure rather than general parametric knowledge.

Source: arXiv:2603.01421 (March 2026).

### End-to-End AI Research Automation (Nature, 2026)

Nature, DOI:10.1038/s41586-026-10265-5. Reports on the first demonstration of
end-to-end automation of AI research at scale, including automated literature
review, model ideation, implementation, evaluation, and paper submission.

**Key finding**: Automated systems can now produce research that clears the bar
for publication at major AI venues, though with important caveats about novelty
evaluation.

---

## The Closed-Loop Framework

Frontiers in Artificial Intelligence (2026, DOI:10.3389/frai.2026.1678539)
describes the generative closed-loop scientific cycle:

```
Literature Mining
        ↓
Hypothesis Generation (LLM + structured reasoning)
        ↓
Experimental Design (Bayesian optimization, active learning)
        ↓
Automated Execution (wet lab robots OR computational experiments)
        ↓
Data Analysis (LLM + statistical pipeline)
        ↓
Manuscript Draft (LLM)
        ↓
Automated Peer Review (LLM critic)
        ↓
[feeds back into Literature Mining]
```

**Current human-in-the-loop points** (required as of 2026):
- Final approval of experimental execution in wet labs
- Validation of novel empirical claims
- Judgment on research directions at programme level
- Ethics and biosafety review
- Final publication decision

---

## New Epistemological Problems

### Who Owns the Hypothesis?

When an LLM generates a hypothesis from its training data (which contains
millions of papers), is it:
1. Producing a genuinely novel inference from the literature?
2. Recombining existing hypotheses in a statistically likely but not truly novel way?
3. Reproducing something from its training data it "remembers" as if generating it?

This is not yet resolvable. The 2025 homogenization research (arXiv 2501.19361:
Wenger & Kenett, tested across 22 LLMs and 102 humans using the Alternative Uses
Test, Forward Flow, and Divergent Association Task) shows LLM creative outputs are
significantly less diverse than human outputs even across different models from
different organizations. Whether this same convergence applies to scientific
hypothesis generation remains an open empirical question, but the underlying
mechanism - shared training distributions across all major LLMs - is the same.

### The Evaluation Problem

Systems like The AI Scientist evaluate their own peer review. A model that is
biased toward certain kinds of results will pass its own outputs through peer
review and fail to catch its own systematic errors. This is the LLM equivalent
of a human researcher who both designs and evaluates their own studies without
blinding.

### Scale and False Discovery

If AI systems generate 100× more hypotheses and experiments, the false discovery
rate problem is amplified. Even at a 5% false positive rate, 100× more
experiments yields 100× more spurious findings. We do not yet have
infrastructure to track provenance and replicate AI-generated claims at scale.

### Epistemic Provenance

Traditional science has clear epistemic provenance: a human had an idea,
designed a study, collected data, analyzed it, and staked their career on the
claim. AI-generated science has diffuse provenance - no individual is
accountable for the hypothesis, the design, or the interpretation.

This creates a new need: **epistemic provenance tracking** - metadata that
records what was human-decided, what was AI-generated, and with what level of
human review at each step.

---

## The Most Consequential Near-Term Development

The combination of:
- Robotic wet labs (Emerald Cloud Lab, Strateos, automated synthesis platforms)
- LLM-based experimental design
- Bayesian optimization for experiment selection
- Automated data analysis

...means the closed loop is nearly complete for chemistry and biology. As of
2026, human scientists still needed at the programme level and for validation.
The transition from AI-as-tool to AI-as-autonomous-scientist is happening within
a single research generation.

---

## Key Sources

- Jumper et al. (2021). AlphaFold. *Nature*, 596, 583–589.
  DOI:10.1038/s41586-021-03819-2
- Merchant et al. (2023). GNoME. *Nature*, 624, 80–85.
  DOI:10.1038/s41586-023-06735-9
- Lu et al. (2024). The AI Scientist. arXiv:2408.06292.
- Frontiers in AI. (2026). The future of fundamental science led by generative
  closed-loop AI. DOI:10.3389/frai.2026.1678539
- arXiv:2602.07983 (2025). EXPERIGEN.
- arXiv:2603.01421 (2026). SciDER.
- arXiv:2604.05587 (2026). ResearchEVO.
- *Nature*. (2026). Towards end-to-end automation of AI research.
  DOI:10.1038/s41586-026-10265-5
- arXiv:2501.19361 (2025). We're Different, We're the Same: LLM output homogenization.
