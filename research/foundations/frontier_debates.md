# Frontier Debates - Open Questions in Scientific Methodology (2025–2026)

## Overview

This document maps the live, unresolved debates in the philosophy and practice
of science as of 2025–2026. These are not settled questions - they are active
research fronts where reasonable experts disagree.

---

## 1. What Does Scientific Progress Actually Mean?

**The classical answer** (Popper, Lakatos): Science progresses by accumulating
knowledge - adding true (or verisimilar) propositions about the world. Progress
is measured by better theories with greater empirical content and fewer falsified
predictions.

**The challenge** (EJPS, 2025):
Using modern cosmology as a case study, recent work argues this model fails.
In cosmology, evidence and epistemic content are distributed across interconnected
webs of beliefs. You cannot point to a single proposition as "the new knowledge."
Progress is better understood as improved *understanding* - increased coherence,
explanatory integration, and insight - not just knowledge accumulation.

**Why it matters for practice**: If progress is understanding, then how we
evaluate research programmes changes. A paper that produces a new p < 0.05
result but does not improve explanatory integration may be less scientifically
progressive than a conceptual synthesis paper.

Source: EJPS (2025). Scientific progress and modern cosmology.
DOI:10.1007/s13194-025-00686-w

---

## 2. Can Robustness Be a Criterion for Truth?

**The question**: When a finding replicates across multiple methods, datasets,
and analytical choices (robustness), does that provide stronger confirmation than
a single well-designed study?

**Common intuition**: Yes - convergent evidence from independent approaches is
more convincing.

**The formal problem** (EJPS, 2026): The inferential rules governing robustness
have historically been informal. New work (Springer, 2026) derives formal
constraints on robustness-based confirmation:
- Robustness confirms when derivations are genuinely independent
- Independence is rarely perfect; correlated methods share assumptions
- Robustness increases confirmation, but by how much, and under what conditions,
  is now formally constrained rather than intuitive

**Open question**: How do we measure the degree of independence between
methods? This requires a formal epistemology of methods that does not yet exist.

Source: EJPS (2026). Inferential rules for confirmatory robustness.
DOI:10.1007/s13194-026-00722-3

---

## 3. The Demarcation Problem - Revisited by AI

**The classical problem** (Popper): How do we distinguish science from pseudoscience?
Popper's answer: falsifiability.

**The AI complication**: Large language models trained on the scientific
literature can generate hypotheses that are:
- Formally falsifiable
- Written in the genre of scientific prose
- Technically consistent with prior literature
- ...but produced by pattern-matching rather than by any understanding of the
  phenomenon

Is an AI-generated hypothesis that passes peer review *science*? The
demarcation problem is no longer merely about fringe claims (astrology,
homeopathy) but about the core of the research enterprise.

**Open question**: Does the epistemic status of a hypothesis depend on the
cognitive process that generated it, or only on its formal properties and
empirical track record? This maps onto the rationalism/empiricism debate at
a new level.

---

## 4. Exploratory vs. Confirmatory Science - Are They Compatible?

**The pre-registration movement** draws a sharp distinction:
- **Confirmatory research**: Test a specific pre-registered hypothesis.
  Statistical results are interpretable.
- **Exploratory research**: Generate hypotheses from data. Results are
  hypothesis-generating, not confirmatory.

**The tension**: Much important science - especially in genomics, neuroimaging,
and AI - is inherently exploratory. You cannot pre-register a finding you have
not yet looked for. Constraining all science to confirmatory testing would
eliminate discovery.

**The middle ground emerging**: Some journals (e.g., *Nature Human Behaviour*)
are experimenting with formats that allow exploratory results but require
explicit labeling, and restrict inferential claims to the confirmatory component.

**Open question**: Can exploratory and confirmatory analysis coexist within a
single study without contaminating the confirmatory inference? The formal
statistics of this problem are unresolved.

Source: Lakens, D. (2021). The practical alternative to the p value is the
correctly used p value. *Perspectives on Psychological Science*, 16(3), 639–648.
https://doi.org/10.1177/1745691620958012

---

## 5. Incommensurability in the Age of AI

**Kuhn's claim**: Competing scientific paradigms share no neutral language for
comparison. Scientists in different paradigms cannot fully communicate.

**The new form**: When a human scientist and an AI system evaluate the same
evidence, are they operating within commensurable frameworks?

- The AI system was trained on a fixed corpus and optimizes for pattern
  consistency with that corpus
- The human scientist operates within a living research programme with
  background knowledge that is tacit, contextual, and not fully articulable

This is not the same as Kuhnian paradigm incommensurability, but it raises
analogous problems about whether human and AI-generated science are
commensurable evaluation standards.

Source: Stanford Encyclopedia of Philosophy. Incommensurability.
https://plato.stanford.edu/entries/incommensurability/

---

## 6. The Multiple Comparison Problem - Amplified by Data Science

**Classical setting**: If you run 20 statistical tests, you expect one false
positive by chance at α = 0.05. Correction methods (Bonferroni, FDR) adjust
for this.

**The modern amplification**: With large datasets and automated analysis
pipelines:
- Researchers may run thousands of implicit tests (feature selection, model
  comparison, hyperparameter tuning) without formal correction
- Automated hypothesis generation systems like EXPERIGEN run hypothesis search
  algorithmically - the multiple comparison problem is embedded in the search
  procedure, not in a declared set of tests

**Open question**: What is the appropriate statistical framework for hypothesis
search? The standard multiple comparisons corrections assume a fixed, known set
of tests. When the set of tests is generated by a search algorithm, the
corrections don't straightforwardly apply.

---

## 7. AI Peer Review - Augmentation or Replacement?

**Current use**: LLMs are used as writing assistants, literature reviewers, and
first-pass technical checkers at a growing number of journals. Several journals
have adopted LLM-based tools for structural review (grammar, citation format,
statistical reporting checklists).

**The boundary question**: Can an LLM be a valid peer reviewer?

**Arguments for**:
- Can check statistical reporting against ASA guidelines consistently
- Can flag missing effect sizes, underpowered designs, and p-hacking risk
- Available 24/7; solves the reviewer bottleneck

**Arguments against**:
- Trained on past science; may reinforce existing biases and paradigms
- Cannot evaluate the plausibility of novel empirical claims (no ground truth)
- May reward well-written conformist papers over genuinely novel but unusual ones
- Accountability is diffuse; errors cannot be attributed

**Current status**: No major journal has replaced human peer review with AI.
Several use AI as a screening tool before human review. The Nature Portfolio
and Science families both accept AI-assisted manuscript preparation but require
disclosure.

---

## 8. The Reproducibility vs. Generalizability Tension

A study can be perfectly reproducible (same results every time) but not
generalizable (results don't hold in other contexts). The replication crisis
focused attention on reproducibility, but the deeper scientific goal is
generalizability.

**Example**: A psychology experiment that reliably produces an effect in
university students from WEIRD populations (Western, Educated, Industrialized,
Rich, Democratic) may be reproducible without being generalizable to human
psychology.

**Open question**: How should we weight reproducibility vs. generalizability
when evaluating research quality? This requires a theory of scientific
externality that most fields lack.

Source: Henrich, J., Heine, S. J., & Norenzayan, A. (2010). The weirdest
people in the world? *Behavioral and Brain Sciences*, 33(2–3), 61–83.

---

## 9. What Should Count as a Replication?

Even among methodologists who support replication, there is sharp disagreement
about what a successful replication requires:

| Position | Criterion |
|---|---|
| Strict replication | Identical result (within measurement error) |
| Statistical replication | p < 0.05 in the same direction |
| Effect-size replication | Effect size within confidence interval of original |
| Conceptual replication | Same theoretical construct tested with different methods |

These produce very different replication rates for the same set of studies.
The PMC review (2025) documents that replication decisions require explicit
prior probability estimates about the original finding, effect size expectations,
and methodological fidelity - none of which are currently standardized.

Source: PMC/NCBI (2025). How can we make sound replication decisions?
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11804638/

---

## 10. Epistemic Justice in Science

An emerging interdisciplinary field (Miranda Fricker, *Epistemic Injustice*,
2007; extended by feminist philosophy of science and postcolonial STS):

**Testimonial injustice**: Systematic undervaluation of the knowledge claims
of members of certain groups (women, non-Western scientists, early-career
researchers) due to credibility deficits.

**Hermeneutical injustice**: The scientific community lacks the conceptual
tools to understand certain experiences or phenomena because those tools were
developed by a homogeneous group.

**Relevance to methodology**: If the demographics of science affect which
hypotheses get generated, which phenomena get studied, and which findings get
trusted, then the scientific method's claim to objectivity is incomplete
without structural attention to who is doing science.

This is the most contested area - dismissed by some as sociology rather than
philosophy of science, and argued by others to be central to the reliability
of scientific knowledge.

---

## Summary: The Most Active Open Questions

| Question | Status | Why It Matters |
|---|---|---|
| What is scientific progress? | Active debate | Changes how we evaluate research programmes |
| Can robustness formally confirm? | New formal work | Affects multi-study inference |
| AI-generated science - is it science? | Open | Demarcation problem, AI frontier |
| Exploratory-confirmatory compatibility | Partial solutions | All of data science |
| Incommensurability of human and AI reasoning | New problem | AI integration into science |
| Multiple comparisons in search | Unsolved | All automated hypothesis generation |
| AI peer review | Emerging practice | Journal norms forming now |
| Reproducibility vs. generalizability | Underexplored | WEIRD problem, translational science |
| What counts as a replication? | No consensus | All of the replication crisis debate |
| Epistemic justice | Contested | Diversity and reliability of science |

---

## Key Sources

- EJPS (2025). Scientific progress and modern cosmology. DOI:10.1007/s13194-025-00686-w
- EJPS (2026). Inferential rules for confirmatory robustness. DOI:10.1007/s13194-026-00722-3
- PMC/NCBI (2025). Sound replication decisions. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11804638/
- Stanford Encyclopedia of Philosophy. Incommensurability. https://plato.stanford.edu/entries/incommensurability/
- Henrich et al. (2010). The weirdest people in the world? *Behavioral and Brain Sciences*, 33(2–3).
- Fricker, M. (2007). *Epistemic Injustice*. Oxford University Press.
- arXiv:2501.19361 (2025). LLM output homogenization.
- Lakens, D. (2021). The practical alternative to the p value is the correctly
  used p value. *Perspectives on Psychological Science*, 16(3), 639–648.
  https://doi.org/10.1177/1745691620958012
