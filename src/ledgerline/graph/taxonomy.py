"""Fixed compliance topic taxonomy used to link Controls to Requirements."""

from __future__ import annotations

from typing import Literal

TOPICS: dict[str, str] = {
    "aml_program": "AML/CFT program existence, written policies, internal controls, risk-based",
    "aml_officer": "Designated BSA/AML compliance officer",
    "aml_training": "AML training of personnel",
    "aml_independent_testing": "Independent review/testing/audit of the AML program",
    "risk_assessment": "Money laundering / illicit finance risk assessment",
    "cip_kyc": "Customer identification and verification, KYC",
    "cdd_edd": "Customer due diligence, enhanced due diligence",
    "sanctions_screening": "OFAC/sanctions screening, blocking",
    "suspicious_activity": "Transaction monitoring, SAR filing",
    "record_retention": "Record keeping and retention periods",
    "error_resolution_timing": "Consumer error/dispute investigation deadlines, provisional credit",
    "error_resolution_notice": "Notices to consumers about dispute results and extensions",
    "reserve_composition": "Stablecoin reserve assets eligibility and 1:1 backing",
    "reserve_reporting": "Monthly reserve publication, accountant exam, CEO/CFO certification",
    "reserve_rehypothecation": "Prohibition on pledging/rehypothecating/reusing reserves",
    "custody_segregation": "Custody, segregation and commingling of customer/reserve assets",
    "token_freeze_capability": "Ability to block, freeze, seize, burn tokens; lawful orders",
    "redemption": "Redemption policies and timing",
    "ai_human_oversight": "Human oversight, review and escalation for AI systems/agents",
    "ai_governance_inventory": "AI inventory, roles, risk assessment, impact assessment",
    "ai_monitoring": "Monitoring, testing and performance measurement of AI systems",
    "vendor_due_diligence": "Third-party due diligence before onboarding",
    "vendor_contract_terms": "Contract terms: audit rights, data use limits, SLAs, termination",
    "vendor_monitoring": "Ongoing monitoring and periodic reassessment of third parties",
    "data_use_privacy": "Restrictions on use of customer data, model training on data",
}
Topic = Literal[
    "aml_program",
    "aml_officer",
    "aml_training",
    "aml_independent_testing",
    "risk_assessment",
    "cip_kyc",
    "cdd_edd",
    "sanctions_screening",
    "suspicious_activity",
    "record_retention",
    "error_resolution_timing",
    "error_resolution_notice",
    "reserve_composition",
    "reserve_reporting",
    "reserve_rehypothecation",
    "custody_segregation",
    "token_freeze_capability",
    "redemption",
    "ai_human_oversight",
    "ai_governance_inventory",
    "ai_monitoring",
    "vendor_due_diligence",
    "vendor_contract_terms",
    "vendor_monitoring",
    "data_use_privacy",
]
Process = Literal[
    "kyc",
    "disputes",
    "recon",
    "reserves",
    "support",
    "aml_program",
    "ai_governance",
    "vendor_management",
    "records",
]


def topic_glossary() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in TOPICS.items())
