"""
Eligibility & Fee Estimator Engine (estimator_engine.py)
Deterministic rule-assisted calculator cross-referencing candidate percentages,
entrance exams, Mathematics prerequisites, category quotas, merit scholarship slabs,
and hostel fee schedules against indexed university policy norms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


PROGRAM_NORMS: Dict[str, dict] = {
    "MCA": {
        "full_name": "Master of Computer Applications (MCA)",
        "duration": "2 Years (4 Semesters)",
        "min_general_pct": 50.0,
        "min_reserved_pct": 45.0,
        "accepted_exams": ["PGCET", "KMAT", "DSAT"],
        "requires_math_check": True,
        "math_bridge_allowed": True,
        "elig_ref": "POL-ELIG-02",
        "fees": {
            "PGCET": ("PGCET Government Quota", 128000),
            "KMAT": ("University / KMAT Quota", 210000),
            "DSAT": ("University / DSAT Quota", 210000),
        },
        "default_fee": ("University / Management Quota", 210000),
    },
    "MBA": {
        "full_name": "Master of Business Administration (MBA)",
        "duration": "2 Years (4 Semesters)",
        "min_general_pct": 50.0,
        "min_reserved_pct": 45.0,
        "accepted_exams": ["PGCET", "KMAT", "CAT", "MAT", "XAT", "CMAT", "DSAT"],
        "requires_math_check": False,
        "math_bridge_allowed": False,
        "elig_ref": "POL-ELIG-03",
        "fees": {
            "PGCET": ("PGCET Government Quota", 135000),
            "KMAT": ("University / KMAT Quota", 295000),
            "CAT": ("University / CAT Quota", 295000),
            "MAT": ("University / MAT Quota", 295000),
            "XAT": ("University / XAT Quota", 295000),
            "CMAT": ("University / CMAT Quota", 295000),
            "DSAT": ("University / DSAT Quota", 295000),
        },
        "default_fee": ("University / Management Quota", 295000),
    },
    "B.Tech": {
        "full_name": "Bachelor of Technology (B.Tech)",
        "duration": "4 Years (8 Semesters)",
        "min_general_pct": 45.0,
        "min_reserved_pct": 40.0,
        "accepted_exams": ["KCET", "COMED-K", "JEE Main", "DSAT"],
        "requires_math_check": True,
        "math_bridge_allowed": False,
        "elig_ref": "POL-ELIG-01",
        "fees": {
            "KCET": ("KCET Government Quota", 107000),
            "COMED-K": ("COMED-K Quota", 268000),
            "JEE Main": ("University / JEE Quota", 385000),
            "DSAT": ("University / DSAT Direct Quota", 385000),
        },
        "default_fee": ("University / DSAT Direct Quota", 385000),
    },
    "BCA": {
        "full_name": "Bachelor of Computer Applications (BCA)",
        "duration": "3 Years / 4 Years Honours",
        "min_general_pct": 45.0,
        "min_reserved_pct": 40.0,
        "accepted_exams": ["DSAT", "Direct / Merit"],
        "requires_math_check": False,
        "math_bridge_allowed": False,
        "elig_ref": "POL-ELIG-03",
        "fees": {
            "DSAT": ("Standard University Tuition", 145000),
            "Direct / Merit": ("Standard University Tuition", 145000),
        },
        "default_fee": ("Standard University Tuition", 145000),
    },
    "B.Sc.": {
        "full_name": "Bachelor of Science (B.Sc. Data Science / Biotech)",
        "duration": "3 Years (6 Semesters)",
        "min_general_pct": 45.0,
        "min_reserved_pct": 40.0,
        "accepted_exams": ["DSAT", "Direct / Merit"],
        "requires_math_check": False,
        "math_bridge_allowed": False,
        "elig_ref": "POL-ELIG-03",
        "fees": {
            "DSAT": ("Standard University Tuition", 115000),
            "Direct / Merit": ("Standard University Tuition", 115000),
        },
        "default_fee": ("Standard University Tuition", 115000),
    },
}

HOSTEL_PLANS: Dict[str, int] = {
    "None": 0,
    "Triple Sharing Non-AC": 95000,
    "Twin Sharing Non-AC": 120000,
    "Twin Sharing AC": 155000,
    "Single AC": 195000,
}

RESERVED_CATEGORIES = {"SC/ST", "Category-1"}


@dataclass
class EstimationResult:
    program: str
    program_full_name: str
    duration: str
    percentage: float
    category: str
    entrance_exam: str
    entrance_rank: Optional[int]
    has_math: bool
    eligible: bool
    eligibility_status: str
    eligibility_reasons: List[str]
    quota_label: str
    gross_tuition_fee: int
    scholarship_pct: int
    scholarship_label: str
    scholarship_discount: int
    net_tuition_fee: int
    registration_fee: int
    exam_library_fee: int
    caution_deposit: int
    hostel_plan: str
    hostel_annual_fee: int
    hostel_security_deposit: int
    total_year1_payable: int
    govt_scholarship_note: str
    citations: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_eligibility_and_fee(
    program: str,
    percentage: float,
    entrance_exam: str = "PGCET",
    category: str = "General",
    has_math: bool = True,
    hostel_plan: str = "None",
    entrance_rank: Optional[int] = None,
) -> EstimationResult:
    """Evaluates eligibility and computes itemized Year-1 fee + merit scholarship."""
    prog_key = program.strip()
    if prog_key not in PROGRAM_NORMS:
        raise ValueError(f"Unsupported program: {program}")

    norms = PROGRAM_NORMS[prog_key]
    pct = max(0.0, min(100.0, float(percentage)))
    cat = category.strip()
    exam = entrance_exam.strip()
    hostel = hostel_plan.strip() if hostel_plan.strip() in HOSTEL_PLANS else "None"

    is_reserved_relaxed = cat in RESERVED_CATEGORIES
    required_pct = (
        norms["min_reserved_pct"] if is_reserved_relaxed else norms["min_general_pct"]
    )

    reasons: List[str] = []
    citations: List[str] = [norms["elig_ref"], "POL-FEES-01"]

    marks_ok = pct >= required_pct
    if marks_ok:
        reasons.append(
            f"Qualifying aggregate {pct:.1f}% meets the minimum {required_pct:.0f}% threshold for {cat} category [{norms['elig_ref']}]."
        )
    else:
        reasons.append(
            f"Qualifying aggregate {pct:.1f}% is below the required {required_pct:.0f}% threshold for {cat} category [{norms['elig_ref']}]."
        )

    exam_ok = exam in norms["accepted_exams"]
    if exam_ok:
        reasons.append(
            f"Entrance pathway '{exam}' is an approved admission exam for {prog_key} [{norms['elig_ref']}]."
        )
    else:
        reasons.append(
            f"'{exam}' is not listed among accepted exams for {prog_key} ({', '.join(norms['accepted_exams'])}) [{norms['elig_ref']}]."
        )

    math_ok = True
    conditional_bridge = False
    if norms["requires_math_check"]:
        if has_math:
            reasons.append(
                f"Mathematics prerequisite satisfied (studied at 10+2 / Graduation level) [{norms['elig_ref']}]."
            )
        elif norms["math_bridge_allowed"]:
            conditional_bridge = True
            reasons.append(
                "No Mathematics at 10+2 or Graduation: Eligible conditionally subject to completing the mandatory Semester-1 Discrete & Foundation Mathematics Bridge Course [POL-ELIG-02]."
            )
        else:
            math_ok = False
            reasons.append(
                f"Physics & Mathematics at 10+2 are compulsory for {prog_key} admission [{norms['elig_ref']}]."
            )

    eligible = marks_ok and exam_ok and math_ok
    if not eligible:
        eligibility_status = "Not Eligible"
    elif conditional_bridge:
        eligibility_status = "Conditionally Eligible (Bridge Course)"
    else:
        eligibility_status = "Eligible"

    # Fee & Quota lookup
    quota_label, gross_tuition = norms["fees"].get(exam, norms["default_fee"])

    # Merit Scholarship Slabs (POL-SCHOL-01)
    pct_waiver = 0
    pct_label = "No Merit Slab (< 85%)"
    if pct >= 95.0:
        pct_waiver = 50
        pct_label = "Slab A: 50% Merit Scholarship (>= 95%)"
    elif pct >= 90.0:
        pct_waiver = 25
        pct_label = "Slab B: 25% Merit Scholarship (90.0% - 94.99%)"
    elif pct >= 85.0:
        pct_waiver = 15
        pct_label = "Slab C: 15% Merit Scholarship (85.0% - 89.99%)"

    rank_waiver = 0
    rank_label = ""
    if entrance_rank is not None and entrance_rank > 0 and exam in {"KCET", "PGCET"}:
        if entrance_rank <= 500:
            rank_waiver = 50
            rank_label = f"Entrance Rank Excellence: 50% Waiver ({exam} Rank {entrance_rank} <= 500)"
        elif entrance_rank <= 2000:
            rank_waiver = 25
            rank_label = f"Entrance Rank Excellence: 25% Waiver ({exam} Rank {entrance_rank} <= 2000)"

    if rank_waiver > pct_waiver:
        scholarship_pct = rank_waiver
        scholarship_label = rank_label
    else:
        scholarship_pct = pct_waiver
        scholarship_label = pct_label

    if not eligible:
        scholarship_pct = 0
        scholarship_label = "Not Applicable (Eligibility Criteria Not Met)"
    else:
        citations.append("POL-SCHOL-01")

    scholarship_discount = int(round(gross_tuition * (scholarship_pct / 100.0)))
    net_tuition = gross_tuition - scholarship_discount

    registration_fee = 10000
    exam_library_fee = 12000
    caution_deposit = 5000

    hostel_annual_fee = HOSTEL_PLANS[hostel]
    hostel_deposit = 15000 if hostel_annual_fee > 0 else 0
    if hostel_annual_fee > 0:
        citations.append("POL-FEES-02")

    total_payable = (
        net_tuition
        + registration_fee
        + exam_library_fee
        + caution_deposit
        + hostel_annual_fee
        + hostel_deposit
    )

    if cat in {"SC/ST", "OBC", "Category-1"}:
        govt_note = (
            f"Candidate under {cat} category may additionally apply via Karnataka SSP / National Scholarship Portal (NSP) before October 31 subject to family income limits [POL-SCHOL-02]."
        )
        citations.append("POL-SCHOL-02")
    else:
        govt_note = "Merit scholarship renewal in Year 2 requires >= 8.0 CGPA, zero active backlogs, and >= 85% attendance [POL-SCHOL-01]."

    return EstimationResult(
        program=prog_key,
        program_full_name=norms["full_name"],
        duration=norms["duration"],
        percentage=round(pct, 2),
        category=cat,
        entrance_exam=exam,
        entrance_rank=entrance_rank,
        has_math=has_math,
        eligible=eligible,
        eligibility_status=eligibility_status,
        eligibility_reasons=reasons,
        quota_label=quota_label,
        gross_tuition_fee=gross_tuition,
        scholarship_pct=scholarship_pct,
        scholarship_label=scholarship_label,
        scholarship_discount=scholarship_discount,
        net_tuition_fee=net_tuition,
        registration_fee=registration_fee,
        exam_library_fee=exam_library_fee,
        caution_deposit=caution_deposit,
        hostel_plan=hostel,
        hostel_annual_fee=hostel_annual_fee,
        hostel_security_deposit=hostel_deposit,
        total_year1_payable=total_payable,
        govt_scholarship_note=govt_note,
        citations=citations,
    )
