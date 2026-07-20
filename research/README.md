# EIF Research Foundation

This directory contains the primary-source research backing for every design
decision in the Epistemic Integrity Framework. Each document is a self-contained
literature review with citations, synthesis tables, and explicit connections to
the EIF phase or tool it informs.

---

## Foundations

The historical and philosophical basis of the scientific method, and why it
applies to AI agents.

| File | What it covers | EIF connection |
|---|---|---|
| [`foundations/classical_method.md`](foundations/classical_method.md) | Aristotle → Ibn al-Haytham → Bacon → Newton; scientific loop with failure modes per step; evidence hierarchy | Design rationale for the full DECLARE→RECORD pipeline |
| [`foundations/philosophy_of_science.md`](foundations/philosophy_of_science.md) | Popper, Kuhn, Lakatos, Feyerabend - full comparison matrix; 2025–2026 literature on scientific progress | Popper → FALSIFY; Lakatos → PROGRAMME (progressive/stable/degenerative) |
| [`foundations/deutsch_epistemology.md`](foundations/deutsch_epistemology.md) | 10 Deutsch concepts mapped directly to EIF phases - fallibilism, reach, error correction through criticism, anti-rational memes | The deepest single-document rationale for EIF's design |
| [`foundations/replication_crisis.md`](foundations/replication_crisis.md) | Open Science Collaboration 36% rate; Begley/Ellis 11%; pre-registration; FAIR principles; 2025 US/EU government response | Direct basis for the REPLICATE phase; pre-registration analogy for FALSIFY |
| [`foundations/statistics.md`](foundations/statistics.md) | p-value crisis (ASA 2016 + 2019); Bayesian vs. frequentist spectrum; Lakatos applied to Bayesianism (2025) | Justifies Bayesian updating in CALIBRATE; IMP4 direction law; why SPRT over NHST |
| [`foundations/ai_and_science.md`](foundations/ai_and_science.md) | AlphaFold, GNoME, The AI Scientist v1/v2, EXPERIGEN, ResearchEVO; false discovery amplification; epistemic provenance diffusion | Context for RECORD phase; positions EIF in the AI-scientist landscape |
| [`foundations/frontier_debates.md`](foundations/frontier_debates.md) | 10 open questions in scientific methodology - AI demarcation, multiple comparisons in search, robustness vs. replication | Intellectual boundary conditions for EIF's scope |

---

## AI Agents and the Scientific Method

How current AI agent research addresses (and often fails) the requirements of
scientific reasoning. Each file covers one capability area with full paper
analysis, empirical results, and synthesis tables.

| File | What it covers | EIF connection |
|---|---|---|
| [`ai_agents/overview.md`](ai_agents/overview.md) | Six highest-priority areas where the scientific method applies to AI agents | Navigation index for the full ai_agents/ set |
| [`ai_agents/hypothesis_generation.md`](ai_agents/hypothesis_generation.md) | POPPER (ICML 2025), ExperiGen, HypoAgents, TruthHypo (IJCAI 2025), ALBERT, FERMIACC; 5 architectural requirements | Direct backing for FALSIFY (SPRT, Type-I control) and HYPOTHESIS_AGENDA (entropy-reduction) |
| [`ai_agents/causal_reasoning.md`](ai_agents/causal_reasoning.md) | Pearl causal ladder; disjunctive bias (COLM 2025); Active Inference (3 gaps scaling won't close); SciExplorer; IRIS; Causal-Copilot; PIEVO; CausalEvolve | Full research backing for CAUSAL_GATE v4; IRIS → confound.py; abductive reasoning → evidence_probe.py |
| [`ai_agents/calibration.md`](ai_agents/calibration.md) | HALoGEN (ACL 2025 Outstanding Paper - 86% hallucination); generation vs. verification asymmetry; Physics-Informed Metacognition (37.2% ECE reduction); conformal prediction certificate | Full backing for CALIBRATE phase; HALoGEN → calibrate/ece.py; conformal → calibrate/conformal.py |
| [`ai_agents/multi_agent_review.md`](ai_agents/multi_agent_review.md) | Echo chamber + sycophancy; AI Co-Scientist (Google, tournament evaluation); EvoScientist (persistent memory); Indibator; BioDisco; DASES (Abyss Falsifier) | AI Co-Scientist → multi_critic.py; DASES → adversarial challenge design; missing replicator role → REPLICATE |
| [`ai_agents/provenance.md`](ai_agents/provenance.md) | DeepTRACE 8-dimension audit (citation accuracy 40–80%); DeepReviewer 2.0 (traceable review packages); Research Object paradigm; ISC Global Reporting Standard (2026+) | Full backing for RECORD phase; DeepTRACE → ProvenanceRecord fields; Research Object → eif_record architecture |

---

## Sycophancy

| File | What it covers | EIF connection |
|---|---|---|
| [`sycophancy_bias_research.md`](sycophancy_bias_research.md) | Canonical literature review - Sharma et al., Wei et al., ELEPHANT, CONSENSAGENT, Truth Decay, Turpin CoT faithfulness | Full research backing for SYCOPHANCY_GATE v2 |

---

## How to read this

Start with [`foundations/deutsch_epistemology.md`](foundations/deutsch_epistemology.md)
if you want to understand why EIF is designed the way it is. Start with
[`ai_agents/overview.md`](ai_agents/overview.md) if you want to understand
where current AI agent research falls short.

The canonical synthesis of all of this into EIF's design decisions lives in
[`docs/research_foundation.md`](../docs/research_foundation.md).
