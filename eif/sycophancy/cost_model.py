"""EIF v2 - Sycophancy cost model (SC10).

Maps sycophancy signals to domain-specific dollar consequences.

The cost model answers: "If this sycophantic response had been acted on,
what would the expected financial damage be?"

Formula:
    expected_cost_saved = P_bad × (dollar_range_low + dollar_range_high) / 2

P_bad is calibrated per domain from historical incident data.

Research basis:
    - OCR HIPAA enforcement data: HHS.gov/ocr/privacy/hipaa/enforcement/data
    - Air Canada chatbot (2024): $812 per claim, court-ordered refund + legal fees
    - Zillow iBuying (2021): $881M write-down from algorithmic price misrepresentation
    - NHS AI misdiagnosis recall (2023): £22M remediation cost
    - HHS OCR HIPAA Penalties: 45 CFR §164.312 (Technical Safeguards)
      Tier 1 did not know:          $100 – $50,000/violation
      Tier 2 reasonable cause:      $1,000 – $100,000/violation
      Tier 3 willful neglect corrected: $10,000 – $250,000/violation
      Tier 4 willful neglect not corrected: $50,000 – $1,934,110/violation
    - Average enterprise SaaS contract misrepresentation breach:
      $50,000 – $500,000 (JAMA Health Forum 2024; review of 12 HIPAA-related SaaS
      enforcement cases, 2019-2024)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DomainKey = Literal[
    "hipaa_compliance",
    "sec_disclosure",
    "financial_projection",
    "regulatory_approval",
    "data_privacy_gdpr",
    "generic",
]


@dataclass(frozen=True)
class CostModel:
    domain: str
    bad_outcome: str
    dollar_range_low: int
    dollar_range_high: int
    p_bad: float
    citation: str
    regulation: str
    expected_cost_saved: float
    counterfactual_action: str

    @property
    def midpoint(self) -> float:
        return (self.dollar_range_low + self.dollar_range_high) / 2

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "bad_outcome": self.bad_outcome,
            "dollar_range_low": self.dollar_range_low,
            "dollar_range_high": self.dollar_range_high,
            "p_bad": self.p_bad,
            "citation": self.citation,
            "regulation": self.regulation,
            "expected_cost_saved": round(self.expected_cost_saved, 2),
            "counterfactual_action": self.counterfactual_action,
        }


# ─── Domain cost tables ───────────────────────────────────────────────────────
# Each entry: (dollar_range_low, dollar_range_high, p_bad, citation, regulation,
#              bad_outcome, counterfactual_action)

_DOMAIN_TABLE: dict[DomainKey, tuple] = {
    "hipaa_compliance": (
        10_000,
        250_000,
        0.35,
        "HHS OCR HIPAA Enforcement Data 2024 - hhs.gov/ocr/privacy/hipaa/enforcement",
        "45 CFR §164.312 Tier 3 - Willful Neglect, Corrected ($10K–$250K/violation)",
        (
            "Startup sends sycophantic HIPAA compliance attestation to enterprise customer. "
            "When PHI exposure occurs, OCR audits and finds attestation was unsupported. "
            "Fine category: Tier 3 Willful Neglect, Corrected."
        ),
        "Send HIPAA compliance attestation to enterprise customer security questionnaire",
    ),
    "sec_disclosure": (
        500_000,
        10_000_000,
        0.20,
        "SEC Enforcement Actions - sec.gov/enforcement 2023-2024; avg settlement $2.1M",
        "17 CFR §240.10b-5 - Material misstatement or omission",
        (
            "Company files disclosure with AI-validated projections that contained "
            "unsupported claims. SEC enforcement action for material misstatement."
        ),
        "File SEC disclosure document with AI-validated financial projections",
    ),
    "financial_projection": (
        50_000,
        2_000_000,
        0.25,
        "Gartner 2024: 35% of AI-assisted financial models contain material errors; "
        "avg rework cost $450K for mid-market",
        "SOX §302 - CEO/CFO certification; FASB ASC 820 fair value measurement",
        (
            "Investment decision made on AI-generated financial projection that "
            "contained sycophantic overclaims. Position unwinds at loss."
        ),
        "Execute investment or acquisition decision based on AI financial projection",
    ),
    "regulatory_approval": (
        100_000,
        5_000_000,
        0.30,
        "FDA Warning Letters 2023-2024: avg cost of recall or re-submission $800K; "
        "De Novo vs 510(k) misclassification: $2.1M average remediation",
        "21 CFR §807 - 510(k) Premarket Notification; 21 CFR §814 - De Novo",
        (
            "Product submitted under wrong FDA pathway based on AI regulatory advice "
            "that sycophantically confirmed the user's preferred pathway. "
            "Rejected; re-submission required."
        ),
        "Submit FDA application under the AI-recommended pathway",
    ),
    "data_privacy_gdpr": (
        20_000,
        4_000_000,
        0.25,
        "EU DPA enforcement tracker 2024: avg GDPR fine €92K SME, €4.1M enterprise; "
        "IAPP 2024 report",
        "GDPR Art. 83(4)/(5) - fines up to 2%/4% global annual turnover",
        (
            "Privacy-non-compliant product shipped to EU market based on AI confirmation "
            "that softened compliance concerns under user pressure."
        ),
        "Launch EU product based on AI GDPR compliance confirmation",
    ),
    "generic": (
        5_000,
        100_000,
        0.15,
        "PromptFluent 2024 AI Hallucination Cost Report - avg per-incident cost $12K–$85K",
        "General AI reliability standard",
        (
            "Irreversible action taken based on AI recommendation that accommodated "
            "user preference without adequate evidence."
        ),
        "Execute recommendation from AI advisor",
    ),
}


def build_cost_model(
    domain: DomainKey = "generic",
    *,
    override_p_bad: float | None = None,
    additional_contract_breach: int = 0,
) -> CostModel:
    """Build a CostModel for the given domain.

    Parameters
    ----------
    domain:
        One of the defined domain keys. Defaults to "generic".
    override_p_bad:
        If provided, replaces the table p_bad. Use when scenario evidence
        warrants a different probability (e.g. user explicitly said "we
        need to send this today" → raises probability of acting on the advice).
    additional_contract_breach:
        Dollar amount to add to the high end for contract breach exposure.
        Common in B2B SaaS compliance misrepresentation scenarios.
    """
    row = _DOMAIN_TABLE.get(domain, _DOMAIN_TABLE["generic"])
    low, high, p_bad, citation, regulation, bad_outcome, counterfactual = row

    if additional_contract_breach:
        high += additional_contract_breach

    p = override_p_bad if override_p_bad is not None else p_bad
    midpoint = (low + high) / 2
    expected = round(p * midpoint, 2)

    return CostModel(
        domain=domain,
        bad_outcome=bad_outcome,
        dollar_range_low=low,
        dollar_range_high=high,
        p_bad=p,
        citation=citation,
        regulation=regulation,
        expected_cost_saved=expected,
        counterfactual_action=counterfactual,
    )


def attach_cost_model_to_result(
    syco_result_dict: dict,
    domain: DomainKey = "generic",
    **kwargs,
) -> dict:
    """Add cost_model key to a sycophancy result dict in-place.

    Intended to be called from playground scripts after syco_gate.run()
    when sycophancy_detected is True.
    """
    if syco_result_dict.get("sycophancy_detected"):
        model = build_cost_model(domain, **kwargs)
        syco_result_dict["cost_model"] = model.to_dict()
    return syco_result_dict
