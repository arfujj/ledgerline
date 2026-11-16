# 90-Day Roadmap

> Prepared by Ledgerline for NovaPay Inc. · November 16, 2026 · run eng-demo-001 · model claude-haiku-5-5 · review status: pending: 33

> AI-generated draft from a SYNTHETIC data room (NovaPay is fictional). Every statement is traceable to a source document, data query or model assumption listed under Sources. This is not legal advice.

Quick wins and critical remediations start in the first 30 days; strategic bets are staged across days 31-90 behind human-oversight and validation gates.

| Window | Track | Action | Owner | Value | Ref |
|---|---|---|---|---|---|
| Days 0-30 | quick win | Real-time document quality checks at upload to cut manual review and rework | COO | NPV $29,666; payback 20.4 mo | OPP-KYC-PRECHECK [1] [2] [3] [4] |
| Days 0-30 | quick win | Prohibit rehypothecation, pledging, and yield-sharing of reserve assets in the Vaultline MSA. Require segregated, bankruptcy-remote reserve accounts and document any regulator-authorized exception. | Head of Vendor Management | - | F-GAP-11 [5] [6] [7] |
| Days 0-30 | quick win | Make Reg E error timelines mandatory: investigate within 10 business days, issue provisional credit if unresolved, and finish within 45 calendar days. Remove the likely-valid precondition and 'aim' language. | unknown | - | F-GAP-13 [8] [9] [10] |
| Days 0-30 | quick win | Extend CIP and other BSA record retention to five years, add a 1010.370 order-hold procedure tied to order-specified periods, and cross-reference the AML policy to the schedule. | Chief Compliance Officer | - | F-GAP-15 [11] [12] [13] |
| Days 0-30 | quick win | Add an explicit control prohibiting any interest, yield, rewards, or other consideration paid to NovaUSD holders solely for holding, using, or retaining the token, with pre-launch review of promotions and partner arrangements. | Head of Treasury & Reserves | - | F-GAP-16 [14] [15] |
| Days 0-30 | quick win | Amend CTR-PARLEY-2026 to restrict Customer Data use to contracted services and prohibit training or product improvement absent written NovaPay consent; audit other vendor contracts for similar clauses. | Head of Vendor Management | - | F-GAP-20 [16] [17] [18] |
| Days 31-60 | remediation | Bring third-party AI services into the model inventory and risk assessment, revise POL-AI-001::0004, and set a defined review frequency in POL-MRM-001 covering all AI systems, not only quantitative models. | Head of AI Products | - | F-GAP-01 [19] [20] [21] |
| Days 31-60 | remediation | Adopt a documented kill-switch and rollback procedure with named owner, defined performance/outcome triggers (error, complaint, refund-anomaly thresholds), and tested authority to disengage Parley Assist and revert to human handling. | Head of AI Products | - | F-GAP-02 [22] [23] [24] |
| Days 31-60 | remediation | Document Parley Assist knowledge limits, known failure modes, and required human review points (e.g., refunds, dispute reason codes, confidence thresholds) and make them available to decision-makers and support staff. | Head of Vendor Management | - | F-GAP-03 [25] [22] [26] |
| Days 31-90 | strategic bet | Dispute intake automation with enforced Reg E provisional-credit timers and human review | COO | NPV $745,994; payback 10.0 mo | OPP-DSP-INTAKE [27] [2] [28] [4] |
| Days 31-90 | strategic bet | Automate reconciliation exception matching (parse RTP/Cardinal references) | COO | NPV $135,118; payback 16.9 mo | OPP-RECON-MATCH [29] [2] [30] [4] |
| Days 61-90 | fill in | AI-assisted EDD workbench (human decision retained) to relieve the 2-person bottleneck | COO | NPV $57,715; payback 21.3 mo | OPP-EDD-ASSIST [1] [2] [31] [4] |

## Sources

1. Data query q_6c3385b55d50: metric 'activity_stats' (process=kyc) over NovaPay event logs; result hash a65647f9dcda1a1f.
2. Data query q_6de719023521: metric 'monthly_volume' (process=kyc) over NovaPay event logs; result hash fe6b1ce0e6f9a8c4.
3. Model assumption 'automation_rate_kyc_doc_precheck': base 0.4 fraction (range 0.25-0.55). Share of manual reviews avoided by real-time document quality checks at upload.
4. Model assumption 'discount_rate': base 0.1 fraction/year (range 0.08-0.14). Hurdle rate for NPV.
5. Master Services Agreement: Vaultline Custody Trust (CTR-VAULTLINE-2026), page 1.
6. NovaUSD Reserve Management Procedure (SOP-RSV-001), section '2. Reserve Composition'.
7. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 4(a)(7). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
8. Complaints Management Policy (POL-CMP-001), section '2. Handling Standard'.
9. Card Dispute and Chargeback Handling Procedure (SOP-DSP-001), section '3. Provisional Credit'.
10. 12 CFR 1005.11 Procedures for resolving errors (Regulation E) (CFR-12-1005.11), clause 1005.11(b). https://www.ecfr.gov/current/title-12/section-1005.11
11. Anti-Money Laundering and Bank Secrecy Act Policy (POL-AML-001), section '6. Recordkeeping'.
12. Records and Data Retention Policy (POL-DR-001), section '2. Retention Schedule'.
13. 31 CFR 1010.430 Nature of records and retention period (CFR-31-1010.430), clause 1010.430(d). https://www.ecfr.gov/current/title-31/section-1010.430
14. NovaUSD Reserve Management Procedure (SOP-RSV-001), section '4. Redemption'.
15. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 4(a)(11). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
16. Third-Party and Vendor Risk Management Policy (POL-VRM-001), section '4. Minimum Contract Terms'.
17. Master Services Agreement: VerifID Ltd. (CTR-VERIFID-2025), page 1.
18. Third-Party and Vendor Risk Management Policy (POL-VRM-001), section ''.
19. Artificial Intelligence Acceptable Use Policy (POL-AI-001), section '5. Model Inventory and Risk Assessment'.
20. Model Risk Management Standard (POL-MRM-001), section '1. Scope'.
21. Artificial Intelligence Risk Management Framework (AI RMF 1.0) (NIST-AI-100-1), page 10. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
22. Artificial Intelligence Acceptable Use Policy (POL-AI-001), section '3. Autonomy of AI Agents'.
23. Parley Assist Support Agent Runbook (SOP-AIS-001), section '2. Escalation'.
24. Artificial Intelligence Risk Management Framework (AI RMF 1.0) (NIST-AI-100-1), page 37. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
25. Master Services Agreement: Parley AI Inc. (CTR-PARLEY-2026), page 1.
26. Artificial Intelligence Risk Management Framework (AI RMF 1.0) (NIST-AI-100-1), page 31. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
27. Data query q_4eb045ef72b5: metric 'activity_stats' (process=disputes) over NovaPay event logs; result hash f5ba06dfff6b066e.
28. Model assumption 'automation_rate_dispute_intake': base 0.35 fraction (range 0.2-0.5). Share of manual dispute intake/notification effort removed with AI-assisted intake under human oversight.
29. Data query q_4dfffa3b7a9d: metric 'activity_stats' (process=recon) over NovaPay event logs; result hash 2888399f96d17e4c.
30. Model assumption 'automation_rate_recon_matching': base 0.7 fraction (range 0.5-0.85). Share of manual reconciliation steps removable by rules-based + ML matching with RTP/Cardinal reference parsing.
31. Model assumption 'automation_rate_edd_assist': base 0.3 fraction (range 0.15-0.45). Analyst time saved per EDD case by AI-assisted evidence gathering and draft memos (human decision retained).
