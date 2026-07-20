# The Replication Crisis - State of the Field

## What Is the Replication Crisis?

The replication crisis refers to a widespread failure across multiple scientific
disciplines to reproduce the results of published studies. It is not a new
problem, but it became a formal field of study after a series of landmark
papers beginning around 2011.

It is increasingly reframed as a "credibility revolution" - a productive
forcing function for structural reform rather than evidence that science is
broken.

---

## Key Terminology

These three terms are frequently conflated but are technically distinct
(Nature Communications, 2024):

| Term | Definition |
|---|---|
| **Reproducibility** | Same data + same analysis → same result. A computational/analytical check. |
| **Robustness** | Same data + different analysis → same result. Tests analytical flexibility. |
| **Replicability** | New data + new study → same result. The true empirical test of generalization. |

Failure at any level is a problem, but failure at the replicability level is
the most serious because it implies the original finding may not describe a
real, stable phenomenon.

---

## Landmark Studies That Defined the Crisis

### The Open Science Collaboration (2015)
*Science*, 349(6251), aac4716.

Attempted to replicate 100 psychology studies published in top journals.
Results:
- Only **36%** of replications achieved statistical significance (39% by subjective rating)
- Mean effect size in replications was **~50% of the original**
- Many effects were real but considerably overstated in the original literature

This is the study that put the crisis on the map for the broader scientific
community.

Source: Open Science Collaboration. (2015). Estimating the reproducibility of
psychological science. *Science*, 349(6251).
https://doi.org/10.1126/science.aac4716

### Begley & Ellis - Cancer Research (2012)
*Nature*, 483, 531–533.

Amgen researchers attempted to replicate 53 landmark cancer research studies.
Only **6 of 53 (11%)** replicated successfully. A separate Bayer analysis
replicated only 25% of their own preclinical studies.

Source: Begley, C. G., & Ellis, L. M. (2012). Raise standards for preclinical
cancer research. *Nature*, 483, 531–533.
https://doi.org/10.1038/483531a

### Many Labs Projects (2014–2018)
Replicated classic social psychology effects across many labs simultaneously.
Findings: some effects are highly robust (e.g., anchoring), others near zero
(e.g., ego depletion as originally operationalized).

---

## Root Causes

### Questionable Research Practices (QRPs)

- **p-hacking**: Trying multiple analyses until p < 0.05, then reporting only
  that result
- **HARKing** (Hypothesizing After Results are Known): Presenting post-hoc
  hypotheses as if they were a priori
- **Selective reporting**: Publishing only significant outcomes; filing away
  null results (the "file drawer problem")
- **Underpowered studies**: Small samples produce large effect size estimates
  by chance (winner's curse); these are less likely to replicate
- **Flexible stopping**: Analyzing data as it accumulates and stopping when
  significance is reached (inflates false positive rate)

### Structural Incentives

- Journals preferentially publish significant, novel results (publication bias)
- Careers are built on "discoveries," not null results or replications
- Replication studies are seen as unoriginal and are rarely funded
- Peer review cannot catch fraud or QRPs - it evaluates plausibility, not data
  integrity

### The Winner's Curse (Button et al., 2013)

When a study is underpowered, a statistically significant result is selected
from a noisy distribution. The observed effect size is therefore necessarily
larger than the true effect size. First published results systematically
overestimate effect sizes - this alone can explain much of the replication
failure rate.

Source: Button, K. S. et al. (2013). Power failure: why small sample size
undermines the reliability of neuroscience. *Nature Reviews Neuroscience*, 14,
365–376. DOI: 10.1038/nrn3475

**Note on Gelman & Loken (2014)**: Their contribution is the related but
distinct "garden of forking paths" concept - that data-dependent analytic
flexibility generates inflated significance even without explicit p-hacking.
Both mechanisms contribute to the replication failure rate.

---

## The Current State (2025)

### Government Response (US, 2025)

The White House Presidential Commission to Make America Healthy Again identified
the replication crisis as its **#1 science integrity recommendation**.

- NIH Director Jay Bhattacharya committed to systemic changes incentivizing
  reproducibility
- The Paragon Health Institute proposed allocating at least 0.1% of the NIH
  annual budget (~$48M/year) specifically to fund replication studies
- Debate continues over whether this represents genuine reform or political
  interference in science

Source: *Chemical & Engineering News* (ACS), June 2025.
https://cen.acs.org/research-integrity/reproducibility/

### Expert Assessment

Brian Nosek (Center for Open Science, founder of the reproducibility initiative):
> "If we define a crisis as something that's changing for the worse, we don't
> have the evidence to say that's happening."

The data on whether things are improving, stable, or declining is genuinely
unclear - because we now detect problems we previously could not see.

---

## Reforms Underway

### Pre-registration

Researchers publicly register their hypotheses, study design, and analysis plan
*before* collecting data. This separates:
- **Confirmatory research**: Testing a specific pre-registered hypothesis
- **Exploratory research**: Generating new hypotheses (must be labeled as such)

Pre-registration does not prevent exploratory analysis - it just requires
researchers to be honest about what was planned vs. discovered.

Source: Nosek, B. A., et al. (2018). The preregistration revolution. *PNAS*,
115(11), 2600–2606. https://doi.org/10.1073/pnas.1708274114

### Registered Reports

A two-stage peer review format now adopted by 300+ journals (Nature
Communications, Nature Neuroscience, Scientific Reports, Cortex, and many others):

**Stage 1**: Hypothesis and methods reviewed *before* data collection.
Journal issues "in-principle acceptance" if the design is sound.

**Stage 2**: Full paper reviewed after data collection. Acceptance based on
methodological adherence, not the result.

**Effect**: Eliminates publication bias by committing to publication before
outcomes are known. Replications and null results become publishable.

Sources:
- Chambers, C. D. (2013). Registered Reports: A new publishing initiative at
  *Cortex*. *Cortex*, 49(3), 609–610.
- Nature Neuroscience adopts Registered Reports for all neurosciences (2024).
  https://www.nature.com/articles/s41593-024-01762-9

### Open Data and Open Methods

- **FAIR principles** (Findable, Accessible, Interoperable, Reusable) for
  scientific data - increasingly required by funders (NIH, European Research
  Council)
- **OSF** (Open Science Framework, osf.io): Free repository for pre-registrations,
  data, and materials
- Code sharing mandates increasing: most Nature Portfolio journals now require
  data and code availability statements

### Effect Size and Confidence Intervals

Moving away from binary p < 0.05 to:
- Effect size reporting (Cohen's d, η², r)
- Confidence interval widths to show precision
- Power analysis to ensure studies can detect real effects

---

## Fields Most Affected

| Field | Replication rate | Notes |
|---|---|---|
| Social psychology | ~36% stat. sig. / ~39% subjectively rated (Open Science Collaboration) | Many underpowered studies, QRP-prone designs |
| Cancer biology | ~11% (Begley/Ellis), ~25% (Bayer) | Preclinical studies; translational gap |
| Economics | ~61% (Camerer et al., 2016) | Higher than psychology |
| Clinical medicine | Highly variable | Publication bias in RCTs well-documented |
| Neuroimaging (fMRI) | Highly variable; Botvinik-Nezer et al. (2020) showed 70 teams analyzing the same dataset reached different conclusions - no two teams used identical pipelines | Analytical flexibility is the core problem, not replication per se |
| Physics | Very high | Theory more constrained; measurement more precise |
| Chemistry | High for synthetic methods; lower for biological effects | |

---

## Positive Reframing

The LSE replication crisis review (2023, eprints.lse.ac.uk/126937/) documents
that the crisis has produced genuinely positive structural changes:

- More replication studies are being funded and published
- Methods transparency norms have improved markedly
- Statistical education is improving
- Fraud detection tools are better (SPRITE, granularity analysis, image forensics)
- The scientific community is more epistemically humble about effect sizes

The crisis revealed a measurement problem, not necessarily a crisis of science
itself. We now know the literature was over-confident. That is progress.

---

## Key Sources

- Open Science Collaboration. (2015). *Science*, 349(6251). DOI:10.1126/science.aac4716
- Begley & Ellis. (2012). *Nature*, 483, 531–533. DOI:10.1038/483531a
- Nosek et al. (2018). The preregistration revolution. *PNAS*, 115(11).
- Ioannidis, J. P. A. (2005). Why most published research findings are false.
  *PLOS Medicine*, 2(8), e124. DOI:10.1371/journal.pmed.0020124
- Nature Communications. (2024). Reproducibility and transparency: what's going
  on and how can we help. https://www.nature.com/articles/s41467-024-54614-2
- Chambers, C. D. (2013). Registered Reports. *Cortex*, 49(3), 609–610.
- LSE Research Online. (2023). The replication crisis has led to positive
  structural, procedural, and community changes. *Communications Psychology*.
  https://eprints.lse.ac.uk/126937/
- PMC/NCBI. (2025). How can we make sound replication decisions?
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11804638/
- ACS Chemical & Engineering News. (2025). Amid White House claims of a research
  'replication crisis,' scientists offer solutions.
  https://cen.acs.org/research-integrity/reproducibility/
