# Automation Opportunity & ROI Summary

> Prepared by Ledgerline for NovaPay Inc. · November 16, 2026 · run eng-demo-001 · model claude-haiku-5-5 · review status: pending: 33

> AI-generated draft from a SYNTHETIC data room (NovaPay is fictional). Every statement is traceable to a source document, data query or model assumption listed under Sources. This is not legal advice.

Hours saved come from mined event logs (data queries); value, cost, ramp and discount rate come from the stated assumptions. NPV is 3-year, shown as conservative / base / optimistic.

| ID | Opportunity | Priority | Hours/yr | Value/yr | Implementation | NPV low/base/high | Payback (mo) | Sources |
|---|---|---|---|---|---|---|---|---|
| OPP-DSP-INTAKE | Dispute intake automation with enforced Reg E provisional-credit timers and human review | strategic bet | 3,347 | $477,585 | $150,000 | $-90,186 / $745,994 / $2,766,656 | 10.0 | [1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11] |
| OPP-RECON-MATCH | Automate reconciliation exception matching (parse RTP/Cardinal references) | strategic bet | 2,322 | $157,865 | $140,000 | $-218,871 / $135,118 / $543,534 | 16.9 | [12] [2] [13] [4] [5] [14] [7] [15] [9] [16] |
| OPP-EDD-ASSIST | AI-assisted EDD workbench (human decision retained) to relieve the 2-person bottleneck | fill in | 572 | $112,615 | $120,000 | $-244,025 / $57,715 / $487,174 | 21.3 | [17] [2] [18] [4] [5] [19] [20] [21] [9] [22] [23] |
| OPP-KYC-PRECHECK | Real-time document quality checks at upload to cut manual review and rework | quick win | 753 | $51,174 | $60,000 | $-116,427 / $29,666 / $289,670 | 20.4 | [17] [2] [24] [4] [5] [25] [7] [26] [9] [27] |
| OPP-SUP-STATUS | Supervised AI agent for status inquiries with mandatory escalation and QA sampling | deprioritize | 379 | $25,749 | $70,000 | $-159,454 / $-46,634 / $45,057 | 74.5 | [2] [28] [29] [4] [5] [30] [7] [31] [9] |

## Largest sensitivities (one-at-a-time, NPV)

| Opportunity | Assumption | NPV at low | NPV at high | Source |
|---|---|---|---|---|
| OPP-RECON-MATCH | automation_rate_recon_matching | $36,618 | $208,993 | [13] |
| OPP-RECON-MATCH | impl_cost_recon_matching | $195,013 | $30,302 | [14] |
| OPP-KYC-PRECHECK | touch_min_kyc_manual_review | $-10,170 | $96,060 | [27] |
| OPP-KYC-PRECHECK | automation_rate_kyc_doc_precheck | $-15,149 | $74,482 | [24] |
| OPP-EDD-ASSIST | value_edd_conversion | $-26,608 | $184,199 | [23] |
| OPP-EDD-ASSIST | impl_cost_edd_assist | $117,610 | $-32,127 | [19] |
| OPP-DSP-INTAKE | value_reg_e_risk_reduction | $441,148 | $1,457,301 | [11] |
| OPP-DSP-INTAKE | touch_min_dispute_manual_step | $591,820 | $1,054,342 | [10] |
| OPP-SUP-STATUS | impl_cost_status_agent | $-9,200 | $-106,529 | [30] |
| OPP-SUP-STATUS | ai_deflection_status_tickets | $-66,028 | $-27,240 | [29] |

## Assumptions appendix

| Assumption | Base | Range | Unit | Rationale |
|---|---|---|---|---|
| ai_deflection_status_tickets | 0.45 | 0.3-0.6 | fraction | Share of status-inquiry tickets resolvable by a supervised AI agent with mandatory escalation rules. |
| automation_rate_dispute_intake | 0.35 | 0.2-0.5 | fraction | Share of manual dispute intake/notification effort removed with AI-assisted intake under human oversight. |
| automation_rate_edd_assist | 0.3 | 0.15-0.45 | fraction | Analyst time saved per EDD case by AI-assisted evidence gathering and draft memos (human decision retained). |
| automation_rate_kyc_doc_precheck | 0.4 | 0.25-0.55 | fraction | Share of manual reviews avoided by real-time document quality checks at upload. |
| automation_rate_recon_matching | 0.7 | 0.5-0.85 | fraction | Share of manual reconciliation steps removable by rules-based + ML matching with RTP/Cardinal reference parsing. |
| discount_rate | 0.1 | 0.08-0.14 | fraction/year | Hurdle rate for NPV. |
| horizon_years | 3 | 3-3 | years | Evaluation horizon. |
| impl_cost_dispute_intake | 150000 | 100000-220000 | USD | Intake automation, Reg E timer controls, human review queue, validation. |
| impl_cost_edd_assist | 120000 | 80000-180000 | USD | LLM-assisted EDD workbench with audit trail and model risk validation. |
| impl_cost_kyc_doc_precheck | 60000 | 40000-90000 | USD | Vendor feature enablement + app changes. |
| impl_cost_recon_matching | 140000 | 100000-210000 | USD | Matching rules, reference parsers, exception workflow; vendor config + 1 engineer for 4 months. |
| impl_cost_status_agent | 70000 | 45000-110000 | USD | Agent scoping, escalation policy, QA sampling, vendor contract remediation. |
| loaded_cost_compliance_hourly | 92 | 75-115 | USD/hour | Fully loaded compliance analyst cost. |
| loaded_cost_ops_hourly | 68 | 55-85 | USD/hour | Fully loaded operations analyst cost (salary + benefits + overhead), US fintech mid-market benchmark. |
| ramp_months_dispute | 6 | 4-9 | months | Time to value. |
| ramp_months_edd | 5 | 4-8 | months | Time to value. |
| ramp_months_kyc_precheck | 2 | 1-3 | months | Time to value. |
| ramp_months_recon | 4 | 3-6 | months | Time to value. |
| ramp_months_status_agent | 3 | 2-5 | months | Time to value. |
| run_cost_pct_of_impl | 0.2 | 0.12-0.3 | fraction/year | Annual run, licensing and maintenance as a share of implementation cost. |
| touch_min_dispute_manual_step | 12 | 8-20 | minutes | Specialist time per manual dispute step (triage, evidence request, notification). |
| touch_min_kyc_edd_review | 35 | 25-50 | minutes | Analyst time per enhanced due diligence review. |
| touch_min_kyc_manual_review | 9 | 6-14 | minutes | Analyst time per manual document review. |
| touch_share_recon_elapsed | 0.75 | 0.6-0.9 | fraction | Share of elapsed time before manual reconciliation steps that is hands-on analyst work (steps run back-to-back the same morning; the remainder is waiting on banks/processors). |
| value_edd_conversion | 60000 | 20000-120000 | USD/year | Revenue retained from fewer onboarding drop-offs when EDD wait falls (illustrative). |
| value_reg_e_risk_reduction | 250000 | 100000-600000 | USD/year | Expected annual reduction in Reg E remediation/restitution and supervisory risk from enforced provisional-credit timers (illustrative expected-loss estimate). |

## Sources

1. Data query q_4eb045ef72b5: metric 'activity_stats' (process=disputes) over NovaPay event logs; result hash f5ba06dfff6b066e.
2. Data query q_6de719023521: metric 'monthly_volume' (process=kyc) over NovaPay event logs; result hash fe6b1ce0e6f9a8c4.
3. Model assumption 'automation_rate_dispute_intake': base 0.35 fraction (range 0.2-0.5). Share of manual dispute intake/notification effort removed with AI-assisted intake under human oversight.
4. Model assumption 'discount_rate': base 0.1 fraction/year (range 0.08-0.14). Hurdle rate for NPV.
5. Model assumption 'horizon_years': base 3 years (range 3-3). Evaluation horizon.
6. Model assumption 'impl_cost_dispute_intake': base 150000 USD (range 100000-220000). Intake automation, Reg E timer controls, human review queue, validation.
7. Model assumption 'loaded_cost_ops_hourly': base 68 USD/hour (range 55-85). Fully loaded operations analyst cost (salary + benefits + overhead), US fintech mid-market benchmark.
8. Model assumption 'ramp_months_dispute': base 6 months (range 4-9). Time to value.
9. Model assumption 'run_cost_pct_of_impl': base 0.2 fraction/year (range 0.12-0.3). Annual run, licensing and maintenance as a share of implementation cost.
10. Model assumption 'touch_min_dispute_manual_step': base 12 minutes (range 8-20). Specialist time per manual dispute step (triage, evidence request, notification).
11. Model assumption 'value_reg_e_risk_reduction': base 250000 USD/year (range 100000-600000). Expected annual reduction in Reg E remediation/restitution and supervisory risk from enforced provisional-credit timers (illustrative expected-loss estimate).
12. Data query q_4dfffa3b7a9d: metric 'activity_stats' (process=recon) over NovaPay event logs; result hash 2888399f96d17e4c.
13. Model assumption 'automation_rate_recon_matching': base 0.7 fraction (range 0.5-0.85). Share of manual reconciliation steps removable by rules-based + ML matching with RTP/Cardinal reference parsing.
14. Model assumption 'impl_cost_recon_matching': base 140000 USD (range 100000-210000). Matching rules, reference parsers, exception workflow; vendor config + 1 engineer for 4 months.
15. Model assumption 'ramp_months_recon': base 4 months (range 3-6). Time to value.
16. Model assumption 'touch_share_recon_elapsed': base 0.75 fraction (range 0.6-0.9). Share of elapsed time before manual reconciliation steps that is hands-on analyst work (steps run back-to-back the same morning; the remainder is waiting on banks/processors).
17. Data query q_6c3385b55d50: metric 'activity_stats' (process=kyc) over NovaPay event logs; result hash a65647f9dcda1a1f.
18. Model assumption 'automation_rate_edd_assist': base 0.3 fraction (range 0.15-0.45). Analyst time saved per EDD case by AI-assisted evidence gathering and draft memos (human decision retained).
19. Model assumption 'impl_cost_edd_assist': base 120000 USD (range 80000-180000). LLM-assisted EDD workbench with audit trail and model risk validation.
20. Model assumption 'loaded_cost_compliance_hourly': base 92 USD/hour (range 75-115). Fully loaded compliance analyst cost.
21. Model assumption 'ramp_months_edd': base 5 months (range 4-8). Time to value.
22. Model assumption 'touch_min_kyc_edd_review': base 35 minutes (range 25-50). Analyst time per enhanced due diligence review.
23. Model assumption 'value_edd_conversion': base 60000 USD/year (range 20000-120000). Revenue retained from fewer onboarding drop-offs when EDD wait falls (illustrative).
24. Model assumption 'automation_rate_kyc_doc_precheck': base 0.4 fraction (range 0.25-0.55). Share of manual reviews avoided by real-time document quality checks at upload.
25. Model assumption 'impl_cost_kyc_doc_precheck': base 60000 USD (range 40000-90000). Vendor feature enablement + app changes.
26. Model assumption 'ramp_months_kyc_precheck': base 2 months (range 1-3). Time to value.
27. Model assumption 'touch_min_kyc_manual_review': base 9 minutes (range 6-14). Analyst time per manual document review.
28. Data query q_a0c47b36306e: metric 'ticket_categories' () over NovaPay event logs; result hash 89c2490101100051.
29. Model assumption 'ai_deflection_status_tickets': base 0.45 fraction (range 0.3-0.6). Share of status-inquiry tickets resolvable by a supervised AI agent with mandatory escalation rules.
30. Model assumption 'impl_cost_status_agent': base 70000 USD (range 45000-110000). Agent scoping, escalation policy, QA sampling, vendor contract remediation.
31. Model assumption 'ramp_months_status_agent': base 3 months (range 2-5). Time to value.
