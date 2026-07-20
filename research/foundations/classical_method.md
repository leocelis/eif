# Classical Foundations of the Scientific Method

## Overview

The scientific method is an iterative epistemological framework for acquiring
reliable knowledge about the natural world. It is not a single fixed procedure
but a family of related practices unified by commitment to empirical testing,
transparency, and falsifiability.

---

## Historical Origins

### Ancient Roots

The earliest systematic attempts at empirical inquiry appear in:

- **Aristotle** (384–322 BCE): Distinguished between inductive reasoning (from
  particular observations to general principles) and deductive reasoning (from
  general principles to specific conclusions). His *Posterior Analytics* laid
  groundwork for the logic of scientific demonstration.

- **Ibn al-Haytham** (965–1040 CE): Considered the first true practitioner of the
  experimental method. His *Book of Optics* (*Kitab al-Manazir*) used controlled
  experiments to study light and vision, establishing observation → hypothesis →
  experiment → conclusion as a working cycle centuries before the European
  Enlightenment.
  Source: Gorini, R. (2003). "Al-Haytham, the man of experience." *Journal of
  the International Society for the History of Islamic Medicine*, 2(4), 53–55.

### The Scientific Revolution (16th–17th century)

- **Francis Bacon** (1561–1626): *Novum Organum* (1620) argued against Aristotelian
  deduction and championed systematic induction - observation of particulars to
  derive general laws. Introduced the concept of systematic tabulation of
  observations to guard against cognitive biases.

- **Galileo Galilei** (1564–1642): Combined mathematics with controlled
  experiment. His work on motion (inclined planes, pendulums) established that
  nature speaks in the language of mathematics and that quantities, not
  qualities, are the subject of science.

- **René Descartes** (1596–1650): *Discourse on the Method* (1637) - championed
  systematic doubt and deductive reasoning from first principles.

- **Isaac Newton** (1643–1727): *Principia Mathematica* (1687) synthesized the
  experimental-inductive and mathematical-deductive traditions. Newton's
  "Rules of Reasoning in Philosophy" remain foundational: prefer simpler
  explanations, generalize from observed phenomena, treat inductive conclusions
  as approximately true until disconfirmed.

---

## The Classical Loop

```
Observation
    ↓
Question (What explains this?)
    ↓
Hypothesis (Falsifiable prediction)
    ↓
Experiment (Controlled test)
    ↓
Data Collection & Analysis
    ↓
Conclusion (Support / Reject / Refine hypothesis)
    ↓
Publication & Peer Review
    ↓
Replication (independent verification)
    ↓
[back to Observation - with updated knowledge]
```

Each step has explicit requirements:

| Step | Core requirement | Common failure mode |
|---|---|---|
| Observation | Documented, reproducible | Confirmation bias in what gets noticed |
| Hypothesis | Must be falsifiable | Vague or unfalsifiable claims |
| Experiment | Controls, blinding, randomization | Confounding variables |
| Analysis | Pre-specified tests, effect sizes | p-hacking, HARKing |
| Peer review | Independent, expert | Pal review, reviewer fatigue |
| Replication | New data, independent lab | File drawer effect |

---

## Core Concepts

### Falsifiability

A hypothesis is scientific only if it is possible, in principle, to demonstrate
that it is false. "All swans are white" is scientific because one black swan
falsifies it. "Everything happens for a reason" is not scientific because no
possible observation could refute it.

Introduced by Karl Popper (*The Logic of Scientific Discovery*, 1934/1959).
See also: `philosophy_of_science.md`.

### Operationalization

Abstract concepts must be converted into measurable, observable proxies before
they can be tested. "Intelligence" is not directly observable; IQ score on a
specified test is an operationalized proxy. The validity of operationalization
is itself empirically contestable.

### Controls and Variables

- **Independent variable**: What the experimenter manipulates
- **Dependent variable**: What the experimenter measures
- **Control variables**: Everything held constant to isolate the IV-DV relationship
- **Control group**: Receives no treatment; baseline comparison
- **Placebo control**: Rules out expectation effects

### Randomization and Blinding

- **Randomization**: Random assignment of subjects to conditions prevents
  systematic confounding by unmeasured variables
- **Single-blind**: Subjects unaware of condition assignment
- **Double-blind**: Both subjects and researchers unaware (gold standard in
  clinical trials to prevent unconscious bias in measurement)

### Statistical Significance vs. Practical Significance

Statistical significance (p < 0.05) indicates only that the observed effect is
unlikely under the null hypothesis at a given sample size. It does not indicate:
- The size of the effect
- Whether the effect matters in practice
- Whether the finding will replicate

Effect size (Cohen's d, r, η²) measures practical magnitude independently of
sample size. Both are necessary; neither alone is sufficient.
See also: `statistics.md`.

---

## Types of Scientific Claims

| Claim type | Nature | Example |
|---|---|---|
| Descriptive | What is the case | "Water boils at 100°C at sea level" |
| Causal | What causes what | "Smoking increases lung cancer risk" |
| Predictive | What will happen | "Adding X will decrease Y by Z%" |
| Mechanistic | How does it work | "mTOR pathway regulates cell growth" |
| Normative | What should be done | Outside empirical science; requires value judgment |

---

## Standards of Evidence

From weakest to strongest (in biomedical and social sciences):

1. Expert opinion / case report
2. Case series
3. Cross-sectional study
4. Case-control study (retrospective)
5. Cohort study (prospective)
6. Randomized controlled trial (RCT)
7. Systematic review + meta-analysis of RCTs

This hierarchy is domain-dependent. In physics, a single experiment with
sufficient theoretical grounding can be definitive. In ecology, RCTs are often
impossible and well-designed observational studies carry more weight.

---

## Key Sources for This Document

- Bacon, F. (1620). *Novum Organum*. London.
- Newton, I. (1687). *Philosophiæ Naturalis Principia Mathematica*.
- Gorini, R. (2003). Al-Haytham, the man of experience. *JIHM*, 2(4), 53–55.
- Gauch, H. G. (2012). *Scientific Method in Brief*. Cambridge University Press.
  ISBN 978-1-107-01607-6.
- Stanford Encyclopedia of Philosophy. (2021). *The Scientific Method*.
  https://plato.stanford.edu/entries/scientific-method/
