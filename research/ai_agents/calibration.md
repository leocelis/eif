# Self-Evaluation, Verification, and Epistemic Calibration in AI Agents

> **Pre-print scope**: POPPER (arXiv:2502.09858, ICML 2025), Vovk et al. conformal
> prediction theory, and HALoGEN (arXiv:2501.08292, ACL 2025 Outstanding Paper) are
> peer-reviewed. Implementation papers arXiv:2601.15808, arXiv:2602.07594,
> arXiv:2602.21368, arXiv:2603.02960 are 2026 pre-prints - treat specific numbers
> as preliminary until published.

## Overview

A scientist who cannot assess the reliability of their own claims is dangerous.
An AI agent that cannot assess the reliability of its own outputs is dangerous
at scale. Epistemic calibration - knowing how certain to be - is not a cosmetic
feature. It is a prerequisite for trustworthy scientific reasoning.

This document covers: the calibration problem in LLMs, the self-verification
gap, current frameworks for improving both, and what "epistemic trustworthiness"
means for an AI agent functioning as a scientific reasoner.

---

## The Calibration Problem

### What Is Calibration?

A system is **well-calibrated** if its expressed confidence matches its
actual accuracy:
- When it says "90% confident," it should be correct ~90% of the time
- When it says "60% confident," it should be correct ~60% of the time

Calibration can be measured with:
- **Expected Calibration Error (ECE)**: average gap between confidence and
  accuracy across probability bins
- **Reliability diagrams**: visual plot of confidence vs. actual accuracy
- **Brier score**: mean squared error of probability forecasts

### LLM Calibration Failures

LLMs are systematically miscalibrated in scientific domains:

- **Overconfidence on false claims**: Models express high confidence on
  hallucinated facts at rates comparable to confidence on true facts
- **Domain dependence**: Calibration is better on common knowledge, worse on
  specialized scientific knowledge (where hallucination is most dangerous)
- **Prompt sensitivity**: Calibration degrades dramatically with leading
  questions, authoritative framing, or suggestions embedded in context

Source: Ravichander et al. (2025). HALoGEN: Fantastic LLM Hallucinations and Where
to Find Them. arXiv:2501.08292. ACL 2025 Outstanding Paper. (150,000 generations
across 14 models; up to 86% of atomic facts hallucinated in domain-specific cases.)

---

## The Self-Verification Gap

### Generation vs. Verification Asymmetry

A fundamental empirical finding (arXiv:2602.07594, 2026):

> **LLMs are significantly weaker at verifying answers than generating them.**

This asymmetry is structurally important:
- Generation is autoregressive: each token is conditioned on all prior tokens.
  The model generates fluent continuations of plausible text.
- Verification requires checking a claim against reality or logical constraints.
  This is a different cognitive operation - one that requires something closer
  to systematic doubt than fluent continuation.

The asymmetry means: an AI agent that generates a hypothesis and then
immediately checks it with the same model has not obtained independent
verification. It has obtained a second pass of the same generative process.

**Empirical result**: Training on self-verification can improve generation
performance. Multi-task reinforcement learning (joint generation + verification
objective) yields better outcomes than generation-only training. This suggests
the skills are learnable but require explicit training signal.

Source: arXiv:2602.07594 (2026). Learning to self-verify.

---

## POPPER's Type-I Error Control (Revisited)

From `hypothesis_generation.md`, POPPER's sequential testing
framework is the strongest current solution to the calibration problem at the
validation level:

- Does not rely on the model's internal confidence estimates (which are
  unreliable)
- Instead implements **external** sequential testing with statistical
  guarantees (SPRT, group sequential designs)
- The Type-I error rate (false positive rate) is controlled at level α
  regardless of how many tests are run

This is the algorithmic equivalent of pre-registration: by committing to a
testing procedure upfront, the agent cannot retroactively inflate confidence.

Source: arXiv:2502.09858 (2025). POPPER.

---

## Physics-Informed Metacognition

**Paper**: Roy, M. et al. (2025). Physics-Informed Metacognition: Improving LLMs
Self-Knowledge via Physical Constraints. OpenReview.
https://openreview.net/forum?id=LF4RSTZUtA

### The Insight

Domain structure constrains what can be true. If an AI agent knows that
temperature must be positive in Kelvin, that conservation laws must hold,
that probability distributions must sum to 1 - then these constraints can
anchor calibration.

### Method

Embedding physical constraints directly into the model's metacognitive process:
- The agent checks proposed claims against known physical laws before expressing
  confidence
- Constraint violations automatically reduce expressed confidence
- Constraint satisfaction boosts confidence in the direction of the constraint

### Results

- **37.2% reduction** in Expected Calibration Error compared to unconstrained
  models
- Improved selective prediction performance: the agent is better at knowing
  when NOT to answer

**Architectural implication**: Domain knowledge should be encoded as hard
constraints on the output space, not merely as training data. A model that has
seen 10,000 examples of conservation-of-energy doesn't necessarily enforce it;
a model with conservation-of-energy as a hard architectural constraint does.

Source: Roy, M. et al. (2025). Physics-Informed Metacognition: Improving LLMs
Self-Knowledge via Physical Constraints. OpenReview.
https://openreview.net/forum?id=LF4RSTZUtA

---

## Rubric-Guided Inference-Time Verification

**Paper**: arXiv:2601.15808 (2026)
*Inference-Time Scaling of Verification: Self-Evolving Deep Research Agents
via Test-Time Rubric-Guided Verification*

### The Problem

Static trained verifiers go stale: the verification criteria embedded in
training become misaligned with new tasks. This paper proposes inference-time
verification: the agent develops rubrics (verification criteria) at test time,
specifically for the current task.

### Method

```
Task specification
    ↓
Agent generates explicit verification rubric
  (What criteria would a correct answer satisfy? What would falsify it?)
    ↓
Agent generates candidate answer
    ↓
Agent applies rubric to evaluate its own answer
    ↓
Iterative refinement: if rubric not satisfied, revise answer
    ↓
Output: answer + rubric + verification trace (auditable)
```

### Results

- **8–11% accuracy improvement** on challenging reasoning benchmarks
- No additional training required - pure inference-time scaling
- Produces auditable verification traces: why the answer was accepted or rejected

**Key property for science**: The rubric is explicit and task-specific. In
scientific terms, the agent declares its verification criteria before evaluating
its own work - the computational analog of pre-registration.

Source: arXiv:2601.15808 (2026).

---

## Black-Box Reliability Certification

**Paper**: arXiv:2602.21368 (2026)
*Black-Box Reliability Certification for AI Agents via Self-Consistency
Sampling and Conformal Calibration*

### The Problem

For high-stakes scientific claims, informal confidence is insufficient. We need
**formal guarantees** about reliability - statistical certificates that hold
with known probability.

### Method: Conformal Prediction

Conformal prediction (Vovk et al., 2005; Angelopoulos & Bates, 2021) provides
distribution-free coverage guarantees:

```
Given: n labeled examples from the same distribution as test queries
Output: prediction set C(x) such that:
  P(y_true ∈ C(x)) ≥ 1 - α   for any α ∈ (0, 1)
```

This is a formal guarantee: regardless of the model's internal workings,
the output set contains the true answer with at least (1-α) probability.

The paper combines this with self-consistency sampling:
1. Sample k independent answers from the model
2. Use the agreement rate across samples as a nonconformity score
3. Apply conformal calibration to convert agreement rates into certified
   confidence intervals

### Results

Provides distribution-free guarantees at specified confidence levels across
different models and tasks. The guarantee does not require knowing the model's
internals - it is a black-box certificate derived purely from empirical
consistency.

**For science**: This is the formal analog of replication. Instead of running
the experiment once and trusting the result, the agent runs multiple independent
"experiments" (samples) and certifies reliability based on their agreement.

Source: arXiv:2602.21368 (2026).

---

## Architecting Trust in Epistemic AI Agents

**Paper**: arXiv:2603.02960 (2026)
*Architecting Trust in Artificial Epistemic Agents*

This paper takes the broadest view: what does it mean for an AI agent to be
trustworthy as a *knowledge curator* - as an epistemic agent?

### The Three Requirements for Epistemic Trustworthiness

1. **Epistemic competence**: The agent must reliably produce accurate beliefs
   and justifications in its domain. This is the calibration requirement.

2. **Robust falsifiability**: The agent's knowledge claims must be structured
   to be falsifiable - not held dogmatically. An agent that cannot update
   its beliefs in response to disconfirming evidence is not epistemically
   virtuous, regardless of its initial accuracy.

3. **Epistemically virtuous behaviors**: Intellectual honesty (not overstating
   certainty), intellectual humility (acknowledging the limits of knowledge),
   and avoidance of cognitive deskilling (not making users epistemically
   dependent in ways that atrophy their own reasoning).

### The Deskilling Risk

The paper raises a specific concern for AI scientific agents: if researchers
routinely accept AI-generated hypotheses and analyses without independent
verification, their own scientific reasoning skills atrophy. The agent must
be designed to augment scientific thinking, not replace it.

This maps to the replication crisis lesson: a scientific culture that trusts
authority over empirical verification becomes epistemically fragile.

Source: arXiv:2603.02960 (2026).

---

## Synthesis: Calibration Architecture for a Scientific AI Agent

| Problem | Solution | Implementation |
|---|---|---|
| Overconfident hallucination | Physical constraint enforcement | Physics-informed metacognition |
| Generation ≠ verification | Explicit verification training | arXiv:2602.07594 multi-task RL |
| Task-specific verification | Inference-time rubric generation | Rubric-guided verification |
| Formal reliability certificate | Conformal calibration | arXiv:2602.21368 |
| p-hacking equivalent | Sequential testing with Type-I control | POPPER SPRT |
| Epistemic dogmatism | Falsifiability-structured knowledge | arXiv:2603.02960 |
| Deskilling risk | Human-in-the-loop at key decisions | Epistemic trustworthiness framework |

---

## Key Sources

- arXiv:2602.07594 (2026). Learning to self-verify.
- arXiv:2502.09858 (2025). POPPER (Type-I error control).
- OpenReview (2025). Physics-informed metacognition.
- arXiv:2601.15808 (2026). Rubric-guided inference-time verification.
- arXiv:2602.21368 (2026). Black-box reliability certification.
- arXiv:2603.02960 (2026). Architecting trust in epistemic AI agents.
- arXiv:2501.08292 (2025). HALoGEN: Fantastic LLM Hallucinations and Where to Find
  Them. ACL 2025 Outstanding Paper. (Replaces cited arXiv:2509.25868 which could
  not be verified.)
- Angelopoulos, A. N., & Bates, S. (2021). A gentle introduction to conformal
  prediction. arXiv:2107.07511.
