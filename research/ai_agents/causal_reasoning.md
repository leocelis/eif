# Causal Reasoning in AI Agents

> **Pre-print scope**: Most papers cited here are arXiv pre-prints (2025–2026).
> Peer-reviewed: Pearl's do-calculus (Cambridge UP); arXiv:2505.09614 disjunctive bias
> (COLM 2025); arXiv:2510.09217 IRIS (pre-print); arXiv:2603.14575 CausalEvolve
> (ICLR 2026). Remaining papers (SciExplorer, Active Inference, Causal-Copilot, PIEVO
> and others) are pre-prints - treat specific numbers as preliminary.

## Overview

Correlation is not causation. This is the most important sentence in
empirical science and the hardest one for AI agents to operationalize.
Statistical associations are symmetric (A correlates with B = B correlates
with A). Causation is asymmetric (A causes B ≠ B causes A). LLMs trained
on observational text systematically conflate the two.

This document covers: the theory of causal reasoning, documented LLM failures
at causal inference, and the current frontier of AI systems that handle
causation correctly.

---

## The Causal Framework - Pearl's Ladder of Causation

Judea Pearl's framework (introduced in *Causality*, 2000; popularized in
*The Book of Why*, 2018) defines three levels of causal reasoning:

```
Level 1 - Association (Seeing)
  "What is the probability of Y given that I observe X?"
  P(Y | X)
  → Purely statistical; what correlates with what in the data
  → Standard ML and LLMs operate here

Level 2 - Intervention (Doing)
  "What is the probability of Y if I do X (change X deliberately)?"
  P(Y | do(X)) - Pearl's do-calculus
  → Requires a causal model (DAG); not inferable from observational data alone
  → Randomized controlled experiments operate here

Level 3 - Counterfactual (Imagining)
  "What would Y have been if X had been different, given that I observed X = x?"
  P(Y_{X=x'} | X = x, Y = y)
  → Requires structural causal model; cannot be answered from data alone
  → Mechanistic scientific explanation operates here
```

An AI agent doing science must ascend from Level 1 (what the data shows) to
at least Level 2 (what would happen if we intervened) to produce actionable
causal claims. Most current LLM-based systems operate at Level 1 with language
that mimics Level 2.

Source: Pearl, J. (2009). *Causality: Models, Reasoning, and Inference*
(2nd ed.). Cambridge University Press.
Pearl, J., & Mackenzie, D. (2018). *The Book of Why*. Basic Books.

---

## Documented LLM Failures in Causal Reasoning

### The Disjunctive Bias (arXiv:2505.09614, 2025)

A systematic empirical study of causal reasoning in LLMs revealed a specific,
reproducible failure mode:

**What LLMs do well**: Infer disjunctive causal relationships.
"A OR B causes C" - LLMs reliably learn this from training data.

**What LLMs fail at**: Conjunctive causal relationships.
"A AND B together cause C (neither alone is sufficient)" - LLMs
systematically fail here, defaulting to the disjunctive assumption.

This "disjunctive bias" persists across:
- All major model families tested (GPT, Claude, Llama variants)
- All model sizes (scaling does not fix it)
- Multiple framing conditions

**Why it matters for science**: Many real causal mechanisms are conjunctive.
A drug causes a disease only in combination with a genetic predisposition.
A policy reduces crime only when combined with economic conditions. An agent
with disjunctive bias will systematically generate wrong causal hypotheses
about conjunctive mechanisms.

**Partial mitigation**: Test-time sampling methods that explicitly enumerate
and eliminate alternative hypotheses reduce the bias, but do not eliminate it.

Source: arXiv:2505.09614 (2025). Causal reasoning biases in LLM agents.

### Causal Direction Failure

LLMs trained on observational text inherit the ambiguity of that text.
The sentence "brain injury is associated with PTSD" is in the training data.
So is "PTSD is associated with brain injury." A model trained on both cannot
reliably distinguish the causal direction without additional structural signal.

Empirically: models trained on bidirectional co-occurrence patterns in text inherit
directional ambiguity - causal direction is statistically underspecified in training
data relative to experimental evidence. This is documented in the broader causal
reasoning failure literature (see arXiv:2505.09614, COLM 2025, for systematic study).

---

## Active Inference Architecture for Scientific Discovery

**Paper**: arXiv:2506.21329 (2025)
*Active Inference AI Systems for Scientific Discovery*

### Core Architecture

This paper argues that genuine scientific discovery AI requires three
integrated components that current LLM-only systems lack:

```
Component 1: Long-lived research memory
  - Grounded in causal self-supervised foundation models
  - Not just episodic retrieval but causal world models
  - The agent "knows" that changing X will affect Y, not merely that X and Y
    co-occur in the literature

Component 2: Symbolic / neuro-symbolic planner with Bayesian guardrails
  - Plans sequences of experiments as a decision problem
  - Bayesian guardrails prevent overconfident intervention
  - Uncertainty is tracked explicitly, not just expressed in hedged language

Component 3: Persistent knowledge graph
  - Thinking generates novel conceptual nodes
  - Reasoning establishes causal edges (not just co-occurrence edges)
  - Graph structure makes implicit causal claims explicit and auditable
```

### The Three Gaps

The paper identifies three gaps that scaling alone will not close:

1. **Abstraction gap**: Moving from specific observations to general principles
   requires structured abstraction, not just pattern completion
2. **Reasoning gap**: Valid causal inference requires the do-calculus or
   equivalent structural reasoning, not language model autoregression
3. **Reality gap**: Genuine discovery requires interaction with the world
   (experiments, sensors, wet labs), not text generation about the world

**Conclusion**: Human judgment remains architecturally indispensable due to
inherent ambiguity in experimental and simulation feedback. AI can accelerate;
it cannot yet replace the human judgment that closes the reality gap.

Source: arXiv:2506.21329 (2025).

---

## SciExplorer - Equation Discovery in Physical Systems

**Paper**: arXiv:2509.24978 (2025)
*Agentic Exploration of Physics Models*

SciExplorer demonstrates causal reasoning at the level of physical law
discovery:

- **Task**: Given an unknown physical system, recover the equations of motion
- **Method**: LLM-based tool-use agent that designs and executes probing
  experiments on the unknown system
- **Causal operation**: Designing interventions (changing initial conditions,
  applying forces) to distinguish between competing causal models
- **Result**: Recovers equations of motion and infers Hamiltonians across
  mechanical, wave, and quantum physics domains without task-specific instructions

This is Level 2 causation (Pearl's intervention level) - the agent performs
do-calculus style interventions, not just observational correlation.

Source: arXiv:2509.24978 (2025).

---

## IRIS - Causal Discovery from Non-Tabular Data

**Paper**: arXiv:2510.09217 (2025)
*IRIS: An Iterative and Integrated Framework for Verifiable Causal Discovery
in the Absence of Tabular Data*

### The Problem

Standard causal discovery algorithms (PC algorithm, FCI, NOTEARS) require
clean tabular data. Most real scientific data is non-tabular: unstructured
experimental reports, narrative descriptions, images, sensor streams. IRIS
addresses causal discovery in this setting.

### Method

```
Document collection (automated, from relevant literature)
    ↓
Statistical causal discovery (applied to extracted quantitative claims)
    ↓
LLM-based causal analysis (fills gaps where statistics cannot reach)
    ↓
Missing variable identification (what confounders are not in the data?)
    ↓
Causal graph expansion (add missing variables; re-run discovery)
    ↓
Verifiable output (causal graph with confidence scores)
```

Crucially, IRIS identifies **missing variables** - the confounders and
mediators that are absent from the current dataset but whose absence would
invalidate any causal claim. This is the computational implementation of
"controlling for confounders."

Source: arXiv:2510.09217 (2025).

---

## Causal-Copilot - Autonomous Causal Analysis

**Paper**: arXiv:2504.13263 (2025)
*Causal-Copilot: An Autonomous Causal Analysis Agent*

An end-to-end system that automates the full expert-level causal analysis
pipeline:

1. **Causal discovery**: Learning causal structure from data (which variables
   cause which)
2. **Algorithm selection**: Choosing the appropriate causal discovery algorithm
   given data characteristics (continuous, discrete, time-series, confounded)
3. **Causal inference**: Estimating the strength of causal effects after
   structure is known
4. **Result interpretation**: Translating causal graph outputs into
   natural-language causal claims

Evaluated on both tabular and time-series data. Performance matches
expert-level causal analysis on standard benchmarks.

Source: arXiv:2504.13263 (2025).

---

## PIEVO - Anomaly-Driven Causal Discovery

**Paper**: arXiv:2602.06448 (2026)
*PIEVO: Principle-Integrated Evolution for Open-Ended Scientific Discovery*

PIEVO addresses the hardest causal problem: discovering causal mechanisms
that the agent was not looking for. It frames scientific discovery as Bayesian
optimization over an evolving **principle space** (not just hypothesis space):

- **Normal operation**: Agents search within known theoretical framework
- **Anomaly trigger**: When experimental results contradict current principles,
  PIEVO activates an anomaly-driven augmentation mechanism
- **Principle revision**: The agent refines its theoretical worldview at the
  principle level, not just the hypothesis level

This is the computational implementation of Kuhn's paradigm challenge: the
agent does not just update a parameter; it revises the generative framework
from which hypotheses are drawn.

Source: arXiv:2602.06448 (2026).

---

## CausalEvolve - Abductive Causal Reasoning

**Paper**: arXiv:2603.14575 (2026)

CausalEvolve introduces a "causal scratchpad" - an explicit working memory
for causal reasoning steps:

- **Abductive reasoning**: When observed data does not fit existing causal
  models, the agent reasons backward from the unexpected observation to
  hypothesize novel causal factors
- **Surprise pattern inspection**: The agent identifies which data points are
  most surprising given the current causal model - these are the anomalies
  most likely to reveal new mechanisms
- **Novel factor hypothesization**: From surprise patterns, the agent
  generates hypotheses about what unobserved causal factor would explain the
  anomaly

This implements the abduction step of scientific reasoning (Charles Sanders
Peirce's schema): from surprising observation + theory, infer the best
explanatory hypothesis.

Source: arXiv:2603.14575 (2026).

---

## Synthesis: What AI Agents Need to Do Causal Science

| Requirement | Mechanism | System |
|---|---|---|
| Level 2 causation (interventions) | do-calculus or experimental design | SciExplorer, GRACE |
| Level 3 causation (counterfactuals) | Structural causal models | Active Inference framework |
| Confounder identification | Missing variable detection | IRIS |
| Causal direction correctness | Structural asymmetry; active testing | Causal-Copilot |
| Conjunctive mechanism detection | Eliminate disjunctive bias via sampling | arXiv:2505.09614 mitigation |
| Anomaly-driven discovery | Bayesian surprise; principle revision | PIEVO, CausalEvolve |
| Abductive reasoning | Causal scratchpad; backward inference | CausalEvolve |
| Knowledge graph of causal edges | Persistent representation | Active Inference architecture |

---

## Key Sources

- Pearl, J. (2009). *Causality* (2nd ed.). Cambridge University Press.
- arXiv:2505.09614 (2025). LLM causal reasoning biases.
- arXiv:2506.21329 (2025). Active inference AI systems for scientific discovery.
- arXiv:2509.24978 (2025). SciExplorer: Agentic physics exploration.
- arXiv:2510.09217 (2025). IRIS: Verifiable causal discovery.
- arXiv:2504.13263 (2025). Causal-Copilot: Autonomous causal analysis.
- arXiv:2602.06448 (2026). PIEVO: Principle-integrated evolution.
- arXiv:2603.14575 (2026). CausalEvolve: Abductive causal reasoning.
- arXiv:2505.09614 (COLM 2025). Language Agents Mirror Human Causal Reasoning Biases.
  (Replaces arXiv:2509.25868 which could not be verified.)
