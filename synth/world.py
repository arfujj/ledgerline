"""Single source of truth for the fictional NovaPay world. Every artifact is derived from this."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SYNTHETIC_BANNER = "SYNTHETIC: NovaPay Inc. is a fictional company. Generated for Ledgerline demos."


@dataclass(frozen=True)
class Person:
    name: str
    title: str
    team: str
    role: str  # role code used in event logs
    reports_to: str | None = None


@dataclass(frozen=True)
class Vendor:
    vendor_id: str
    name: str
    service: str
    processes: tuple[str, ...]
    criticality: str
    annual_fee_usd: int


@dataclass(frozen=True)
class World:
    company: str = "NovaPay Inc."
    hq: str = "Austin, Texas"
    period_start: date = date(2026, 1, 1)
    period_end: date = date(2026, 9, 30)
    engagement_date: date = date(2026, 11, 16)
    data_extract_date: date = date(2026, 11, 13)  # logs are cut here; later events not seen
    stablecoin_name: str = "NovaUSD"
    stablecoin_launch: date = date(2027, 2, 1)
    loaded_hourly_cost_ops: float = 68.0
    loaded_hourly_cost_compliance: float = 92.0

    # Simulation targets (generator parameters; the answer key stores *measured* values)
    kyc_cases: int = 14_000
    dispute_cases: int = 9_000
    recon_rails: tuple[str, ...] = ("ACH", "CARD", "WIRE", "RTP")
    recon_manual_share_target: float = 0.40
    kyc_rework_rate_target: float = 0.22
    kyc_edd_rate: float = 0.18
    dispute_sla_breach_target: float = 0.18
    dispute_late_provisional_credit_target: float = 0.12
    tickets: int = 5_000

    people: tuple[Person, ...] = field(
        default_factory=lambda: (
            Person("Elena Varga", "Chief Executive Officer", "Executive", "EXEC"),
            Person("Daniel Okafor", "Chief Financial Officer", "Finance", "EXEC", "Elena Varga"),
            Person(
                "Grace Lin",
                "Chief Compliance Officer & BSA Officer",
                "Compliance",
                "CCO",
                "Elena Varga",
            ),
            Person("Tomás Reyes", "Chief Operating Officer", "Operations", "EXEC", "Elena Varga"),
            Person(
                "Aisha Bello",
                "Head of Treasury & Reserves",
                "Treasury",
                "TREASURY_LEAD",
                "Daniel Okafor",
            ),
            Person("Sam Whitaker", "Head of AI Products", "Product", "AI_LEAD", "Tomás Reyes"),
            Person(
                "Priya Raman",
                "Senior Compliance Analyst (EDD)",
                "Compliance",
                "COMPLIANCE_ANALYST",
                "Grace Lin",
            ),
            Person(
                "Marcus Ode",
                "Compliance Analyst (EDD)",
                "Compliance",
                "COMPLIANCE_ANALYST",
                "Grace Lin",
            ),
            Person("Hannah Cole", "KYC Operations Lead", "Operations", "KYC_LEAD", "Tomás Reyes"),
            Person("Leo Martins", "KYC Analyst", "Operations", "KYC_ANALYST", "Hannah Cole"),
            Person("Nadia Petrova", "KYC Analyst", "Operations", "KYC_ANALYST", "Hannah Cole"),
            Person("Omar Haddad", "KYC Analyst", "Operations", "KYC_ANALYST", "Hannah Cole"),
            Person("Julia Brandt", "KYC Analyst", "Operations", "KYC_ANALYST", "Hannah Cole"),
            Person("Kevin Tran", "Disputes Manager", "Operations", "DISPUTES_LEAD", "Tomás Reyes"),
            Person(
                "Rosa Delgado",
                "Disputes Specialist",
                "Operations",
                "DISPUTES_SPECIALIST",
                "Kevin Tran",
            ),
            Person(
                "Ben Adler",
                "Disputes Specialist",
                "Operations",
                "DISPUTES_SPECIALIST",
                "Kevin Tran",
            ),
            Person(
                "Mei Chen", "Disputes Specialist", "Operations", "DISPUTES_SPECIALIST", "Kevin Tran"
            ),
            Person(
                "Ivan Sokolov",
                "Disputes Specialist",
                "Operations",
                "DISPUTES_SPECIALIST",
                "Kevin Tran",
            ),
            Person(
                "Chloe Dubois",
                "Finance Operations Manager",
                "Finance",
                "FINOPS_LEAD",
                "Daniel Okafor",
            ),
            Person(
                "Raj Patel", "Reconciliation Analyst", "Finance", "RECON_ANALYST", "Chloe Dubois"
            ),
            Person(
                "Lucy Grant", "Reconciliation Analyst", "Finance", "RECON_ANALYST", "Chloe Dubois"
            ),
            Person(
                "Felix Wong", "Reconciliation Analyst", "Finance", "RECON_ANALYST", "Chloe Dubois"
            ),
            Person(
                "Zara Ahmed", "Support Team Lead", "Customer Support", "SUPPORT_LEAD", "Tomás Reyes"
            ),
            Person(
                "Victor Hugo Silva",
                "Head of Vendor Management",
                "Procurement",
                "VENDOR_LEAD",
                "Daniel Okafor",
            ),
            Person(
                "Ingrid Holm",
                "Director of Internal Audit",
                "Internal Audit",
                "AUDIT_LEAD",
                "Elena Varga",
            ),
        )
    )

    vendors: tuple[Vendor, ...] = (
        Vendor(
            "V-VERIFID",
            "VerifID Ltd.",
            "Identity document verification API",
            ("kyc",),
            "critical",
            410_000,
        ),
        Vendor(
            "V-LEDGERCORE",
            "LedgerCore Systems",
            "Core ledger and cloud hosting",
            ("kyc", "disputes", "recon"),
            "critical",
            1_250_000,
        ),
        Vendor(
            "V-PARLEY",
            "Parley AI Inc.",
            "LLM-based support and dispute-intake agent",
            ("disputes", "support"),
            "high",
            380_000,
        ),
        Vendor(
            "V-CARDINAL",
            "Cardinal Processing LLC",
            "Card issuing processor",
            ("disputes", "recon"),
            "critical",
            960_000,
        ),
        Vendor(
            "V-VAULTLINE",
            "Vaultline Custody Trust",
            "Stablecoin reserve custody",
            ("reserves",),
            "critical",
            540_000,
        ),
        Vendor(
            "V-RECONWORKS",
            "ReconWorks SaaS",
            "Reconciliation matching software",
            ("recon",),
            "medium",
            145_000,
        ),
    )

    def people_by_role(self, role: str) -> list[Person]:
        return [p for p in self.people if p.role == role]


WORLD = World()
