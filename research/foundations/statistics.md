# The Statistics Wars - p-Values, Bayesian Inference, and the Path Forward

## Overview

The choice of statistical framework is not merely technical - it embodies
commitments about what evidence means, how uncertainty should be represented,
and what science should produce. The debate has sharpened considerably since
the ASA's 2016 statement on p-values and the ongoing fallout from the
replication crisis.

---

## The p-Value Crisis

### What Is a p-Value?

A p-value is the probability of observing data at least as extreme as the
obtained results, *assuming the null hypothesis is true*.

Formally: **P(data | H₀)**

What it is **not** (common misinterpretations):
- Not the probability that the null hypothesis is true
- Not the probability that the result occurred by chance
- Not a measure of effect size or practical importance
- Not the probability that the finding will replicate

### The ASA Statement (2016 + 2019 Task Force)

The American Statistical Association issued a formal statement (Wasserstein &
Lazar, 2016, *The American Statistician*) - the first time in its 177-year
history it took an official position on a statistical method.

**Six principles** (ASA, 2016):
1. P-values can indicate incompatibility between data and a specified model
2. P-values do not measure the probability that the studied hypothesis is true
3. Scientific conclusions should not be based solely on whether a p-value passes
   a threshold
4. Proper inference requires full reporting: effect sizes, confidence intervals,
   adequate descriptions of data collection and all analyses
5. A p-value does not measure the size or importance of an observed effect
6. By itself, a p-value does not provide a good measure of evidence regarding a
   model or hypothesis

The 2019 Task Force went further, explicitly calling for a move into a
**"post p<0.05 era"** and urging the abandonment of the language of
"statistical significance" entirely.

Sources:
- Wasserstein, R. L., & Lazar, N. A. (2016). The ASA's statement on p-values.
  *The American Statistician*, 70(2), 129–133.
  https://doi.org/10.1080/00031305.2016.1154108
- Wasserstein, R. L., Schirm, A. L., & Lazar, N. A. (2019). Moving to a world
  beyond "p < 0.05." *The American Statistician*, 73(sup1), 1–19.
- The ASA President's Task Force Statement on Statistical Significance and
  Replicability. *Annals of Applied Statistics*, 15(3).
  https://projecteuclid.org/journals/annals-of-applied-statistics/volume-15/issue-3/

### What Should Replace It?

No single replacement has achieved consensus. The leading alternatives:

| Alternative | What it provides | Limitation |
|---|---|---|
| **Effect size** (Cohen's d, r, η²) | Magnitude of the effect | Does not account for estimation uncertainty |
| **Confidence intervals** | Range of plausible values | Frequentist CIs are often misinterpreted as probability intervals |
| **Bayesian credible intervals** | Probability that the true value lies in a range | Requires specification of prior |
| **Bayes factors** | Evidence ratio for H₁ vs. H₀ | Sensitive to prior choice; computationally intensive |
| **False discovery rate** (FDR) | Expected proportion of false positives in a list | Context-dependent |
| **Minimum clinically important difference** (MCID) | Threshold for practical importance | Domain-specific; not universally defined |

Recent 2025 consensus (*The Lancet Regional Health – Southeast Asia*,
ScienceDirect): p-values and confidence intervals should be treated as
"compatibility measures" that require contextual interpretation - not
mechanical threshold decisions.

Source: Rovetta, A., Piretta, L., & Mansournia, M. A. (2025). p-Values and
confidence intervals as compatibility measures: guidelines for interpreting
statistical studies in clinical research. *The Lancet Regional Health –
Southeast Asia*, 33. https://www.sciencedirect.com/article/pii/S2772368225000058

---

## Frequentist Statistics

### Core Logic

Probability is defined as the long-run frequency of events over infinitely
repeated trials. Parameters are fixed (unknown) constants; data are random.
The goal is to construct procedures that perform well over the long run.

**Null hypothesis significance testing** (NHST) is the dominant frequentist
framework in most scientific fields:
1. State a null hypothesis H₀ (typically: no effect)
2. Collect data
3. Calculate probability of data (or more extreme) assuming H₀
4. If p < α (usually 0.05), reject H₀

**Invented by**: Ronald A. Fisher (1890–1962) introduced p-values in his 1925
*Statistical Methods for Research Workers*. Jerzy Neyman and Egon Pearson
(1930s) added the H₀/H₁ framework, power, and error rates.

**Strengths**:
- Does not require specification of prior probabilities
- Operationally objective - two analysts with the same data and analysis plan
  must reach the same number
- Standard in clinical trials, regulatory science (FDA), and quality control
- Large body of practice, teaching materials, and software

**Weaknesses**:
- The p-value does not answer the question researchers actually want answered
  ("How likely is H₁?")
- Binary decision framework (significant/non-significant) is a lossy compression
  of continuous evidence
- NHST as practiced (without pre-registration) is highly susceptible to QRPs
- Does not naturally accumulate evidence across studies

---

## Bayesian Statistics

### Core Logic

Probability represents a degree of belief, not a long-run frequency.
Parameters are random variables with probability distributions.
Evidence updates beliefs via Bayes' theorem:

```
P(H | data) = P(data | H) × P(H) / P(data)

Posterior ∝ Likelihood × Prior
```

**Thomas Bayes** (c. 1701–1761) formulated the theorem - his exact birth year
is uncertain (1701 or 1702 in different scholarly sources); **Pierre-Simon Laplace**
(1749–1827) developed it into a practical scientific framework.

**Key concepts**:

| Term | Meaning |
|---|---|
| **Prior** P(H) | Belief in the hypothesis before seeing data |
| **Likelihood** P(data\|H) | How well the hypothesis predicts the observed data |
| **Posterior** P(H\|data) | Updated belief after observing data |
| **Bayes factor** | Ratio of likelihoods: P(data\|H₁) / P(data\|H₀) |
| **Credible interval** | Interval containing the true parameter with stated probability |

**Subjectivist vs. Objectivist Bayesianism**:
- **Subjectivist**: Priors are elicited from expert knowledge or personal belief.
  Principled but susceptible to manipulation.
- **Objectivist**: Attempts to specify "non-informative" or "reference" priors
  that minimize the influence of prior beliefs (Jeffreys priors, reference
  priors, maximum entropy priors). The goal of minimal subjectivity.

Source: A Snapshot of Bayesianism. *MDPI Entropy*, 27(4), 448 (2025).
https://www.mdpi.com/1099-4300/27/4/448

**Strengths**:
- Directly answers "how probable is H given the data?"
- Naturally accumulates evidence across studies (sequential updating)
- Can incorporate prior knowledge explicitly and transparently
- Better suited to complex hierarchical models and prediction
- Dominant framework in machine learning, cognitive science, and decision theory

**Weaknesses**:
- Requires specification of a prior; prior sensitivity can be a problem
- Computationally demanding for complex models (MCMC sampling)
- Multiple valid prior choices can yield different conclusions
- Less familiar to many researchers; software ecosystem still maturing

---

## Five Positions in the Spectrum

The Harvard Data Science Review (HDSR, MIT Press, Issue 6.3, 2024) documents that the
frequentist/Bayesian framing conceals a spectrum of at least 5 positions:

1. **Strict frequentist**: Only long-run frequency probabilities are valid.
   No priors. (Fisher's original position on inference)
2. **Pragmatic frequentist**: Uses NHST as a useful heuristic but acknowledges
   its limits; supplements with effect sizes and CIs.
3. **Eclectic**: Uses both frameworks depending on the research question.
   Bayesian for complex models; frequentist for simple confirmatory tests.
4. **Pragmatic Bayesian**: Uses Bayesian methods but treats priors as
   practical regularization, not epistemic commitments.
5. **Strict Bayesian (subjectivist)**: All inference is Bayesian; probability
   is always a degree of belief; prior elicitation is principled.

The contemporary consensus is that position 3 (eclectic) is the most epistemically defensible, with the choice of framework subordinate to the
research question and context.

Source: Lin, H. (2024). To Be a Frequentist or Bayesian? Five Positions in a
Spectrum. *Harvard Data Science Review*, Issue 6.3.
https://hdsr.mitpress.mit.edu/pub/axvcupj4/release/1

---

## The Lakatos Connection (2025)

A 2025 Springer book chapter ("The Bayesian Research Programme in the
Methodology of Science, or Lakatos Meets Bayes") applies Lakatos's research
programme framework to assess whether Bayesianism is progressive or degenerative.

**Finding**: Bayesianism qualifies as a *progressive research programme* - it
continues to generate solutions to its own challenges (the problem of old
evidence, dynamic coherence, the Dutch book arguments) rather than merely
patching failures ad hoc. This is a positive assessment in Lakatosian terms.

Source: Springer (2025). *The Bayesian Research Programme in the Methodology
of Science*. ISBN 978-3-031-88213-5, Ch. 8.

---

## The Ongoing Debate (2025)

**Context-dependent statistics** (arXiv, 2024 / Dagstuhl Reports, 2024):
The choice of statistical paradigm should align with the specific research
context and the value judgments inherent to its field. Neither Bayesian nor
frequentist methods are universally optimal. "Operational objectivity" - 
the goal of procedures that minimize subjective variance - may be achievable
within both paradigms depending on application.

**Bayesianism in AI and ML** (Dagstuhl Seminar 24461, 2024):
A dedicated research seminar examined Bayesianism's role in modern machine
learning: challenges of computing accurate posteriors in high dimensions,
establishing appropriate benchmarks for Bayesian deep learning, and whether
neural network weights admit a Bayesian interpretation.

---

## Practical Recommendations (Current Best Practice)

From the combined weight of ASA statements, Nature editorials, and 2025
literature:

1. **Always report effect sizes** - p-values without them are uninterpretable
2. **Always report confidence/credible intervals** - point estimates without
   uncertainty ranges are inadequate
3. **Distinguish confirmatory from exploratory analysis** - and label it clearly
4. **Pre-register confirmatory analyses** - prevents QRPs
5. **Report power** - underpowered studies systematically overestimate effects
6. **Match the framework to the question**: Sequential evidence accumulation →
   Bayesian; Regulatory decision boundaries → Frequentist
7. **Do not call findings "significant" or "non-significant"** - describe the
   magnitude and precision of the effect

---

## Key Sources

- Wasserstein & Lazar. (2016). The ASA's statement on p-values. *The American
  Statistician*. https://doi.org/10.1080/00031305.2016.1154108
- ASA President's Task Force. (2021). Statement on statistical significance and
  replicability. *Annals of Applied Statistics*, 15(3).
  https://projecteuclid.org/journals/annals-of-applied-statistics/volume-15/issue-3/
- Lin, H. (2024). To Be a Frequentist or Bayesian? Five Positions in a Spectrum.
  *Harvard Data Science Review*, Issue 6.3. https://hdsr.mitpress.mit.edu/pub/axvcupj4/
- MDPI Entropy. (2025). A Snapshot of Bayesianism. 27(4), 448.
  https://www.mdpi.com/1099-4300/27/4/448
- Dagstuhl Reports. (2024). Report on Seminar 24461 (Bayesianism + AI).
  https://drops.dagstuhl.de/storage/04dagstuhl-reports/volume14/issue11/24461/
- Rovetta et al. (2025). p-Values and confidence intervals as compatibility
  measures. *The Lancet Regional Health – Southeast Asia*, 33.
  https://www.sciencedirect.com/article/pii/S2772368225000058
- Springer. (2025). The Bayesian Research Programme in the Methodology of
  Science. ISBN 978-3-031-88213-5.
