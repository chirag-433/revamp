import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from complaints.models import (
    BureauCell,
    CanonicalStatus,
    CaseAction,
    CaseLink,
    ComplaintCase,
    Institution,
    InstitutionAlias,
    InstitutionMatchStatus,
    StatusMap,
)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

BUREAUS = {
    "RB": "Regulation Bureau",
    "PGRC": "Public Grievance Redressal Cell",
    "ACADEMIC": "Academic Coordination Cell",
    "APPROVAL": "Approval Bureau",
    "PLANNING": "Planning and Coordination Cell",
}

STATES_AND_DISTRICTS = [
    ("Maharashtra", "Pune", "West"),
    ("Maharashtra", "Mumbai", "West"),
    ("Maharashtra", "Nagpur", "West"),
    ("Karnataka", "Bengaluru", "South"),
    ("Karnataka", "Mysuru", "South"),
    ("Tamil Nadu", "Chennai", "South"),
    ("Tamil Nadu", "Coimbatore", "South"),
    ("Kerala", "Kochi", "South"),
    ("Kerala", "Thiruvananthapuram", "South"),
    ("Telangana", "Hyderabad", "South"),
    ("Andhra Pradesh", "Visakhapatnam", "South"),
    ("Gujarat", "Ahmedabad", "West"),
    ("Gujarat", "Surat", "West"),
    ("Rajasthan", "Jaipur", "North"),
    ("Rajasthan", "Jodhpur", "North"),
    ("Uttar Pradesh", "Lucknow", "North"),
    ("Uttar Pradesh", "Noida", "North"),
    ("Uttar Pradesh", "Kanpur", "North"),
    ("Delhi", "New Delhi", "North"),
    ("Madhya Pradesh", "Bhopal", "Central"),
    ("Madhya Pradesh", "Indore", "Central"),
    ("West Bengal", "Kolkata", "East"),
    ("Odisha", "Bhubaneswar", "East"),
    ("Bihar", "Patna", "East"),
    ("Assam", "Guwahati", "North East"),
    ("Punjab", "Chandigarh", "North"),
    ("Haryana", "Gurugram", "North"),
    ("Jharkhand", "Ranchi", "East"),
    ("Chhattisgarh", "Raipur", "Central"),
    ("Uttarakhand", "Dehradun", "North"),
]

INSTITUTION_WORDS = [
    ["Sahyadri", "Vivekananda", "National", "Bharati", "Lakshmi", "Shri",
     "Dr. Ambedkar", "Mahatma Gandhi", "Netaji", "Aryabhatta", "Raman",
     "Chanakya", "Guru Nanak", "Swami Dayanand", "Sri Aurobindo",
     "Tagore", "Bose", "Ramanujan", "Vikram Sarabhai", "Homi Bhabha",
     "Rajiv Gandhi", "Jawaharlal Nehru", "APJ Abdul Kalam", "Kamaraj",
     "Indira Gandhi", "Sardar Patel", "Subhash Chandra", "Deen Dayal",
     "Lal Bahadur", "Maulana Azad"],
    ["Institute", "College", "School", "Academy", "Centre", "Foundation"],
    ["of Technology", "of Engineering", "of Applied Sciences",
     "of Technical Education", "of Management", "of Computer Science",
     "of Information Technology", "of Science and Technology",
     "of Engineering and Technology", "of Advanced Studies"],
]

CATEGORIES = [
    "Faculty shortage", "Infrastructure deficiency", "Fee or refund dispute",
    "Admission irregularity", "Misleading claims", "Approval or affiliation issue",
    "Academic or examination issue", "Safety or harassment",
    "Student services", "Placement fraud", "Hostel complaints",
    "Lab equipment shortage", "Library access issues",
]

DESCRIPTIONS = [
    "Synthetic complaint about inadequate {category} at the institution.",
    "Synthetic grievance: students report {category} affecting quality of education.",
    "Synthetic report regarding {category} requiring urgent attention.",
    "Synthetic inquiry filed by stakeholders about {category}.",
    "Synthetic case: faculty members raise concern over {category}.",
    "Synthetic request to investigate {category} at this institution.",
    "Synthetic complaint filed through online portal about {category}.",
    "Synthetic grievance about unresolved {category} since last semester.",
]

STATUS_MAPPING = {
    "received": CanonicalStatus.PENDING,
    "pending": CanonicalStatus.PENDING,
    "in progress": CanonicalStatus.UNDER_PROCESS,
    "under process": CanonicalStatus.UNDER_PROCESS,
    "under review": CanonicalStatus.UNDER_PROCESS,
    "action initiated": CanonicalStatus.UNDER_PROCESS,
    "disposed": CanonicalStatus.DISPOSED,
    "closed": CanonicalStatus.DISPOSED,
    "resolved": CanonicalStatus.DISPOSED,
    "transferred": CanonicalStatus.TRANSFERRED,
    "forwarded": CanonicalStatus.TRANSFERRED,
    "escalated": CanonicalStatus.ESCALATED,
}

OFFICERS = [
    "Rajesh Kumar", "Priya Sharma", "Anil Gupta", "Sunita Reddy",
    "Vikram Singh", "Deepa Nair", "Manoj Tiwari", "Kavita Desai",
    "Suresh Babu", "Neha Kapoor", "Ramesh Chand", "Anjali Mishra",
    "Sanjay Verma", "Pooja Patel", "Amit Joshi",
]

ACTION_TYPES = [
    "received", "reviewed", "notice_issued", "response_received",
    "inspection_ordered", "transferred", "escalated",
    "hearing_scheduled", "final_order",
]

# Noise patterns: common abbreviations and typos used to stress the matcher.
NOISE_TRANSFORMS = [
    lambda name: name.replace("Institute", "Inst."),
    lambda name: name.replace("Institute", "Instt"),
    lambda name: name.replace("College", "Coll."),
    lambda name: name.replace("Engineering", "Engg."),
    lambda name: name.replace("Engineering", "Engg"),
    lambda name: name.replace("Technology", "Tech."),
    lambda name: name.replace("Technology", "Tech"),
    lambda name: name.replace("of ", ""),
    lambda name: name.replace(" and ", " & "),
    lambda name: name.replace("Science", "Sci."),
    lambda name: name.replace("Management", "Mgmt"),
    lambda name: name.replace("Computer", "Comp"),
    lambda name: name.replace("Information", "Info"),
    lambda name: " ".join(reversed(name.split()[:3])) + " " + " ".join(name.split()[3:]),
]


class Command(BaseCommand):
    help = "Create or refresh synthetic demo data with noise and planted overlaps."

    def add_arguments(self, parser):
        parser.add_argument(
            "--institutions",
            type=int,
            default=100,
            help="Number of institutions to generate (default 100).",
        )
        parser.add_argument(
            "--cases-per-institution",
            type=int,
            default=4,
            help="Average cases per institution (default 4).",
        )
        parser.add_argument(
            "--overlap-pct",
            type=int,
            default=15,
            help="Percentage of institutions with planted cross-bureau overlaps (default 15).",
        )

    def handle(self, *args, **options):
        rng = random.Random(42)  # reproducible seed
        now = timezone.now()
        num_institutions = options["institutions"]
        avg_cases = options["cases_per_institution"]
        overlap_pct = options["overlap_pct"]

        from django.db import transaction

        with transaction.atomic():
            self.stdout.write("Setting up bureaus and status mappings...")
            bureau_objects = self._create_bureaus()
            self._create_status_mappings()

            self.stdout.write(f"Generating {num_institutions} institutions...")
            institutions = self._create_institutions(rng, num_institutions)

            self.stdout.write("Adding institution aliases with noise...")
            self._create_aliases(rng, institutions)

            self.stdout.write("Generating cases...")
            all_cases = self._create_cases(
                rng, now, institutions, bureau_objects, avg_cases,
            )

            self.stdout.write("Planting cross-bureau overlaps...")
            overlap_count = self._plant_overlaps(
                rng, now, institutions, bureau_objects, overlap_pct,
            )

            self.stdout.write("Running overlap detection on planted data...")
            self._run_detection()

        total_cases = ComplaintCase.objects.count()
        total_links = CaseLink.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Done: {len(institutions)} institutions, {total_cases} cases, "
            f"{total_links} overlap links, {overlap_count} planted overlap institutions."
        ))

    # -----------------------------------------------------------------------

    def _create_bureaus(self):
        bureau_objects = {}
        for code, name in BUREAUS.items():
            obj, _ = BureauCell.objects.update_or_create(
                code=code, defaults={"name": name, "is_active": True},
            )
            bureau_objects[code] = obj
        return bureau_objects

    def _create_status_mappings(self):
        source_systems = list(BUREAUS.keys()) + ["DEMO"]
        for system in source_systems:
            for source_status, canonical in STATUS_MAPPING.items():
                StatusMap.objects.update_or_create(
                    source_system=system,
                    source_status=source_status,
                    defaults={"canonical_status": canonical},
                )

    def _create_institutions(self, rng, count):
        institutions = []
        used_names = set()

        for i in range(count):
            # Generate a unique institution name.
            attempts = 0
            while True:
                prefix = rng.choice(INSTITUTION_WORDS[0])
                kind = rng.choice(INSTITUTION_WORDS[1])
                suffix = rng.choice(INSTITUTION_WORDS[2])
                name = f"{prefix} {kind} {suffix}"
                if name not in used_names:
                    used_names.add(name)
                    break
                attempts += 1
                if attempts > 50:
                    name = f"{prefix} {kind} {suffix} #{i}"
                    used_names.add(name)
                    break

            state, district, region = rng.choice(STATES_AND_DISTRICTS)

            # ~25% of institutions have no Permanent ID (noisy data).
            permanent_id = f"AICTE-{i + 1:04d}" if rng.random() > 0.25 else None

            inst, _ = Institution.objects.update_or_create(
                name=name,
                defaults={
                    "aicte_permanent_id": permanent_id,
                    "district": district,
                    "state": state,
                    "region": region,
                    "address": f"Synthetic address, {district}, {state}",
                    "is_active": True,
                },
            )
            institutions.append(inst)

        return institutions

    def _create_aliases(self, rng, institutions):
        """Add noisy aliases for ~40% of institutions."""
        for inst in institutions:
            if rng.random() > 0.40:
                continue
            transform = rng.choice(NOISE_TRANSFORMS)
            alias_text = transform(inst.name)
            if alias_text != inst.name:
                from complaints.services.normalization import normalize_institution_name
                norm = normalize_institution_name(alias_text)
                InstitutionAlias.objects.update_or_create(
                    institution=inst,
                    normalized_alias=norm,
                    defaults={"alias": alias_text, "source": "synthetic_noise"},
                )

    def _create_cases(self, rng, now, institutions, bureau_objects, avg_cases):
        bureau_codes = list(bureau_objects.keys())
        status_keys = list(STATUS_MAPPING.keys())
        all_cases = []

        for inst in institutions:
            num_cases = max(1, int(rng.gauss(avg_cases, 1.5)))

            for j in range(num_cases):
                bureau_code = rng.choice(bureau_codes)
                bureau = bureau_objects[bureau_code]
                raw_status = rng.choice(status_keys)
                canonical = STATUS_MAPPING[raw_status]
                category = rng.choice(CATEGORIES)
                age_days = rng.randint(2, 180)
                received_at = now - timedelta(days=age_days)

                # Some cases use noisy institution names (~30%).
                if rng.random() < 0.30:
                    transform = rng.choice(NOISE_TRANSFORMS)
                    raw_name = transform(inst.name)
                else:
                    raw_name = inst.name

                # Some cases deliberately have no institution link (~25%).
                has_link = rng.random() > 0.25
                linked_institution = inst if has_link else None
                match_status = (
                    InstitutionMatchStatus.EXACT_ID
                    if has_link and inst.aicte_permanent_id
                    else InstitutionMatchStatus.UNMATCHED
                )

                source_id = f"DEMO-{bureau_code}-{inst.pk:04d}-{j:02d}"
                case_number = f"{bureau_code}-{inst.pk * 100 + j:06d}"

                description = rng.choice(DESCRIPTIONS).format(
                    category=category.lower(),
                )

                sla_days = rng.choice([15, 30, 45, 60])

                case, created = ComplaintCase.objects.update_or_create(
                    source_system="DEMO",
                    source_case_id=source_id,
                    defaults={
                        "case_number": case_number,
                        "institution": linked_institution,
                        "raw_institution_name": raw_name,
                        "match_status": match_status,
                        "bureau": bureau,
                        "category": category,
                        "description": description,
                        "source_status": raw_status,
                        "status": canonical,
                        "assigned_officer": rng.choice(OFFICERS),
                        "received_at": received_at,
                        "last_action_at": received_at + timedelta(days=rng.randint(1, 5)),
                        "next_action": (
                            "Review source documents" if canonical != CanonicalStatus.DISPOSED
                            else "No further action"
                        ),
                        "sla_due_at": received_at + timedelta(days=sla_days),
                        "expected_disposal_at": received_at + timedelta(days=sla_days + 15),
                    },
                )

                # Add 2-6 action history entries.
                num_actions = rng.randint(2, 6)
                for k in range(num_actions):
                    action_time = received_at + timedelta(days=k * rng.randint(1, 5))
                    CaseAction.objects.get_or_create(
                        case=case,
                        action_type=rng.choice(ACTION_TYPES),
                        acted_at=action_time,
                        defaults={
                            "actor_label": rng.choice(OFFICERS),
                            "remarks": f"Synthetic action #{k + 1} for demo.",
                            "from_bureau": bureau,
                        },
                    )

                all_cases.append(case)

        return all_cases

    def _plant_overlaps(self, rng, now, institutions, bureau_objects, pct):
        """
        For a percentage of institutions, ensure they have open cases
        in at least 2 different bureaus — this is our planted ground truth.
        """
        overlap_count = max(1, len(institutions) * pct // 100)
        overlap_institutions = rng.sample(institutions, min(overlap_count, len(institutions)))

        bureau_codes = list(bureau_objects.keys())

        for inst in overlap_institutions:
            # Pick 2 different bureaus.
            b1, b2 = rng.sample(bureau_codes, 2)

            for bureau_code in [b1, b2]:
                bureau = bureau_objects[bureau_code]
                category = rng.choice(CATEGORIES)
                age_days = rng.randint(5, 60)
                received_at = now - timedelta(days=age_days)

                # Use a noisy name variant for one of the two.
                if bureau_code == b2:
                    transform = rng.choice(NOISE_TRANSFORMS)
                    raw_name = transform(inst.name)
                else:
                    raw_name = inst.name

                source_id = f"DEMO-OVERLAP-{bureau_code}-{inst.pk:04d}"
                case_number = f"OVL-{bureau_code}-{inst.pk:04d}"

                case, _ = ComplaintCase.objects.update_or_create(
                    source_system="DEMO",
                    source_case_id=source_id,
                    defaults={
                        "case_number": case_number,
                        "institution": inst,
                        "raw_institution_name": raw_name,
                        "match_status": InstitutionMatchStatus.EXACT_ID if inst.aicte_permanent_id else InstitutionMatchStatus.CONFIRMED,
                        "match_confidence": 1.0 if inst.aicte_permanent_id else 0.85,
                        "bureau": bureau,
                        "category": category,
                        "description": f"Synthetic planted overlap: {category.lower()} complaint via {bureau_code}.",
                        "source_status": "in progress",
                        "status": CanonicalStatus.UNDER_PROCESS,
                        "assigned_officer": rng.choice(OFFICERS),
                        "received_at": received_at,
                        "last_action_at": received_at + timedelta(days=2),
                        "next_action": "Coordinate with other Bureau/Cell",
                        "sla_due_at": received_at + timedelta(days=30),
                    },
                )

                CaseAction.objects.get_or_create(
                    case=case,
                    action_type="received",
                    acted_at=received_at,
                    defaults={
                        "actor_label": "Synthetic seed",
                        "remarks": f"Planted overlap case for {bureau_code}.",
                        "from_bureau": bureau,
                    },
                )

        return len(overlap_institutions)

    def _run_detection(self):
        """Run overlap detection on all seeded data."""
        from complaints.services.overlap import run_full_overlap_scan
        stats = run_full_overlap_scan()
        self.stdout.write(
            f"  Overlap scan: {stats['institutions_scanned']} institutions, "
            f"{stats['links_created']} links created."
        )
