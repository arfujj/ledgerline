# AI Readiness & Compliance Assessment: Executive Memo

> Prepared by Ledgerline for NovaPay Inc. · November 16, 2026 · run eng-demo-001 · model claude-haiku-5-5 · review status: pending: 33

> AI-generated draft from a SYNTHETIC data room (NovaPay is fictional). Every statement is traceable to a source document, data query or model assumption listed under Sources. This is not legal advice.

## Executive summary

Regulatory gaps are critical in three areas: reserve custody permits rehypothecation and yield-sharing that undermine holders' senior claims, Reg E investigation and provisional-credit timelines are advisory rather than mandatory, and BSA record retention falls short of five years for CIP records. [1] [2] [3] CTR-PARLEY-2026 lets the vendor use Customer Data to train models for all customers, contradicting POL-VRM-001, and AI agent autonomy lacks a kill-switch or performance-based escalation trigger. [4] [5] [6] Operationally, 17.0% of disputes (1533 of 9000) miss the 45-day resolution window and 12.2% of disputes receive provisional credit after 10 business days, creating Regulation E exposure. [7] [8] [9] Dispute intake automation with enforced Reg E timers is the highest-value opportunity, with 3,347 annual hours saved, $477,585 annual value, $150,000 implementation cost, $745,994 three-year NPV and 10.0-month payback. [10] [11] [12] Reconciliation matching automation (2,322 hours saved, $135,118 three-year NPV) and the KYC document pre-check (753 hours saved, $29,666 NPV) address 41.6% manual reconciliation and a 22.2% KYC rework loop, while the supervised status agent shows a negative NPV of $-46,634 and should be deprioritized. [13] [14] [11]

## Compliance gaps

The most severe compliance exposure is the Vaultline reserve arrangement, where the custodian may rehypothecate reserves for yield shared with NovaPay, which falls outside permitted activities and undermines holders' senior claims. [1] [2] [3] Reserve commingling compounds this gap, so NovaPay cannot yet demonstrate the segregated, bankruptcy-remote reserve accounts that stablecoin readiness requires. [1] [2] [3] Holder-yield controls are also missing, since no prohibition exists on interest, yield, or rewards paid to NovaUSD holders for holding or using the token. [3] [15] [16] Regulation E error handling is non-compliant: no control meets the 10-business-day investigation and provisional credit timing or the mandatory 45-day outer limit, and 12.2% of disputes receive provisional credit after 10 business days, with 17.0% of disputes missing the 45-day window. [8] [7] [17] AML recordkeeping is deficient because CIP records are retained for only three years post-closure against a five-year BSA requirement, and no 1010.370 order-hold procedure exists. [18] [19] [20] AI oversight is weak: autonomous refunds proceed without employee review, no kill-switch or disengagement authority exists for Parley Assist, and third-party AI sits outside the model inventory. [21] [22] [23]

## Operational inefficiencies

Enhanced Due Diligence Review is a key-person bottleneck, with a median wait of 31.0 hours and only 2 resources performing it. [24] [25] [26] Reconciliation is 41.6% manual, with 3329 of 8009 steps performed as spreadsheet work. [13] [27] [28] 17.0% of disputes miss the 45-day resolution window, with 1533 of 9000 disputes exceeding it, and 12.2% of disputes receive provisional credit after 10 business days, creating Regulation E exposure. [7] [8] [9] Dispute cases average 0.97 specialist handoffs, and KYC 'Manual Document Review' repeats in 22.2% of cases across 3110 cases. [29] [30] [31] The highest-value fixes are dispute intake automation with enforced provisional-credit timers, at $477,585 annual value and a 3-year NPV of $745,994, and reconciliation matching automation, at $157,865 annual value and a 3-year NPV of $135,118. [10] [11] [14]

## Automation opportunities and ROI

Dispute intake automation with enforced Reg E provisional-credit timers ranks first on value, with $477,585 in annual value against a $150,000 implementation cost, a 3-year NPV of $745,994, and a 10.0-month payback. [10] [11] [12] Reconciliation exception matching ranks second, delivering $157,865 in annual value for a $140,000 implementation with a 3-year NPV of $135,118 and a 16.9-month payback. [14] [11] [32] The AI-assisted EDD workbench ($112,615 annual value, $120,000 cost, 3-year NPV $57,715, 21.3-month payback) and KYC document precheck ($51,174 annual value, $60,000 cost, 3-year NPV $29,666, 20.4-month payback) follow as lower-value fill-ins that relieve the two-person EDD bottleneck and manual KYC rework. [33] [11] [24] The supervised AI status agent should be deprioritized: its 3-year NPV is $-46,634 with a 74.5-month payback on a $70,000 implementation, despite 379 annual hours saved. [11] [34] [35]

## Priority findings

- F-GAP-10 (critical): No control: Custody, segregation and commingling of customer/reserve assets. [36] [37]
- F-GAP-11 (critical): Partial coverage: Custody, segregation and commingling of customer/reserve assets (CTR-VAULTLINE-2026, SOP-RSV-001). [1] [2] [3]
- F-GAP-13 (critical): Partial coverage: Consumer error/dispute investigation deadlines, provisional credit (POL-CMP-001, SOP-DSP-001). [17] [38] [9]
- F-GAP-15 (critical): Partial coverage: Record keeping and retention periods (POL-AML-001, POL-DR-001). [18] [19] [20]
- F-GAP-16 (critical): Partial coverage: Redemption policies and timing (SOP-RSV-001). [3] [15] [16]
- F-GAP-17 (critical): No control: Prohibition on pledging/rehypothecating/reusing reserves (CTR-VAULTLINE-2026, SOP-RSV-001). [1] [2] [39]

## Next 90 days

- Days 0-30: Real-time document quality checks at upload to cut manual review and rework; Prohibit rehypothecation, pledging, and yield-sharing of reserve assets in the Vaultline MSA. Require segregated, bankruptcy-remote reserve accounts and document any regulator-authorized exception; Make Reg E error timelines mandatory: investigate within 10 business days, issue provisional credit if unresolved, and finish within 45 calendar days. Remove the likely-valid precondition and 'aim' language (+3 more)
- Days 31-60: Bring third-party AI services into the model inventory and risk assessment, revise POL-AI-001::0004, and set a defined review frequency in POL-MRM-001 covering all AI systems, not only quantitative models; Adopt a documented kill-switch and rollback procedure with named owner, defined performance/outcome triggers (error, complaint, refund-anomaly thresholds), and tested authority to disengage Parley Assist and revert to human handling; Document Parley Assist knowledge limits, known failure modes, and required human review points (e.g., refunds, dispute reason codes, confidence thresholds) and make them available to decision-makers and support staff
- Days 31-90: Dispute intake automation with enforced Reg E provisional-credit timers and human review; Automate reconciliation exception matching (parse RTP/Cardinal references)
- Days 61-90: AI-assisted EDD workbench (human decision retained) to relieve the 2-person bottleneck

## Sources

1. Master Services Agreement: Vaultline Custody Trust (CTR-VAULTLINE-2026), page 1.
2. NovaUSD Reserve Management Procedure (SOP-RSV-001), section '2. Reserve Composition'.
3. NovaUSD Reserve Management Procedure (SOP-RSV-001), section '4. Redemption'.
4. Third-Party and Vendor Risk Management Policy (POL-VRM-001), section '4. Minimum Contract Terms'.
5. Master Services Agreement: VerifID Ltd. (CTR-VERIFID-2025), page 1.
6. Master Services Agreement: Parley AI Inc. (CTR-PARLEY-2026), page 1.
7. Data query q_9a6321c6f5fd: metric 'sla_breach' (process=disputes, threshold_hours=1080) over NovaPay event logs; result hash f47ac5ab351a0c7d.
8. Data query q_819593897bc3: metric 'late_step' (process=disputes, business_days=10, activity=Provisional Credit Issued) over NovaPay event logs; result hash 540f9a7068a0fa5b.
9. Card Dispute and Chargeback Handling Procedure (SOP-DSP-001), section '4. Investigation and Resolution'.
10. Data query q_4eb045ef72b5: metric 'activity_stats' (process=disputes) over NovaPay event logs; result hash f5ba06dfff6b066e.
11. Data query q_6de719023521: metric 'monthly_volume' (process=kyc) over NovaPay event logs; result hash fe6b1ce0e6f9a8c4.
12. Model assumption 'automation_rate_dispute_intake': base 0.35 fraction (range 0.2-0.5). Share of manual dispute intake/notification effort removed with AI-assisted intake under human oversight.
13. Data query q_fccda94b27d8: metric 'manual_share' (process=recon) over NovaPay event logs; result hash caa39f881869b044.
14. Data query q_4dfffa3b7a9d: metric 'activity_stats' (process=recon) over NovaPay event logs; result hash 2888399f96d17e4c.
15. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 4(a)(11). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
16. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 4(a)(1)(B). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
17. Complaints Management Policy (POL-CMP-001), section '2. Handling Standard'.
18. Anti-Money Laundering and Bank Secrecy Act Policy (POL-AML-001), section '6. Recordkeeping'.
19. Records and Data Retention Policy (POL-DR-001), section '2. Retention Schedule'.
20. Records and Data Retention Policy (POL-DR-001), section '3. Legal Holds'.
21. Artificial Intelligence Acceptable Use Policy (POL-AI-001), section '3. Autonomy of AI Agents'.
22. Parley Assist Support Agent Runbook (SOP-AIS-001), section '2. Escalation'.
23. Card Dispute and Chargeback Handling Procedure (SOP-DSP-001), section '2. Intake'.
24. Data query q_bb41b2cadfde: metric 'bottlenecks' (process=kyc, top_n=1) over NovaPay event logs; result hash aaa842d30a1c8099.
25. Data query q_3b93e11a1e12: metric 'resource_load' (process=kyc, activity=Enhanced Due Diligence Review) over NovaPay event logs; result hash 29cab88837b81722.
26. KYC Onboarding Standard Operating Procedure (SOP-KYC-001), section '3. Enhanced Due Diligence'.
27. Daily Cash and Settlement Reconciliation Procedure (SOP-REC-001), section '2. Steps'.
28. Postmortem: RTP reconciliation break carried for 6 days (PM-2026-014), section 'Root Cause'.
29. Data query q_1a2297da53fa: metric 'handoffs' (process=disputes) over NovaPay event logs; result hash de5e332f53bc1012.
30. Data query q_c0b50d3efeaf: metric 'rework_rate' (process=kyc) over NovaPay event logs; result hash 66135a8da522bc0e.
31. Board of Directors Meeting: Q3 2026 Operating Review (Excerpt) (BRD-2026-Q3), page 2.
32. Model assumption 'automation_rate_recon_matching': base 0.7 fraction (range 0.5-0.85). Share of manual reconciliation steps removable by rules-based + ML matching with RTP/Cardinal reference parsing.
33. Data query q_6c3385b55d50: metric 'activity_stats' (process=kyc) over NovaPay event logs; result hash a65647f9dcda1a1f.
34. Data query q_a0c47b36306e: metric 'ticket_categories' () over NovaPay event logs; result hash 89c2490101100051.
35. Model assumption 'ai_deflection_status_tickets': base 0.45 fraction (range 0.3-0.6). Share of status-inquiry tickets resolvable by a supervised AI agent with mandatory escalation rules.
36. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 10(b). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
37. Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27) (GENIUS-ACT-2025), clause 10(d). https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm
38. Card Dispute and Chargeback Handling Procedure (SOP-DSP-001), section '3. Provisional Credit'.
39. NovaUSD Reserve Management Procedure (SOP-RSV-001), section '3. Reporting and Attestation'.
