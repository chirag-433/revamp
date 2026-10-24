from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
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
from complaints.services.matching import (
    find_candidates,
    resolve_institution,
    resolve_unmatched_cases,
)
from complaints.services.overlap import (
    detect_overlaps_for_case,
    detect_overlaps_for_institution,
    review_overlap,
    run_full_overlap_scan,
)


class Phase3MatchingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testofficer", password="password123"
        )
        self.bureau_rb = BureauCell.objects.create(code="RB", name="Regulation Bureau")
        self.bureau_pgrc = BureauCell.objects.create(code="PGRC", name="Public Grievance Redressal Cell")

        self.inst_coep = Institution.objects.create(
            name="College of Engineering Pune",
            aicte_permanent_id="1-1001",
            district="Pune",
            state="Maharashtra",
            region="West",
        )
        self.inst_vjti = Institution.objects.create(
            name="Veermata Jijabai Technological Institute",
            aicte_permanent_id="1-1002",
            district="Mumbai",
            state="Maharashtra",
            region="West",
        )
        # Add alias for COEP
        InstitutionAlias.objects.create(
            institution=self.inst_coep,
            alias="COEP Technological University",
        )

        StatusMap.objects.create(
            source_system="DEMO",
            source_status="in progress",
            canonical_status=CanonicalStatus.UNDER_PROCESS,
        )

    def test_fuzzy_candidates_alias_and_normalized_match(self):
        # Query with exact normalized alias
        candidates = find_candidates("COEP Technological University")
        self.assertTrue(len(candidates) > 0)
        self.assertEqual(candidates[0].institution, self.inst_coep)
        self.assertGreaterEqual(candidates[0].score, 0.90)

    def test_fuzzy_candidates_typo_match(self):
        # Slight typo: "Colege of Enginering Pune"
        candidates = find_candidates("Colege of Enginering Pune")
        self.assertTrue(len(candidates) > 0)
        self.assertEqual(candidates[0].institution, self.inst_coep)
        self.assertGreaterEqual(candidates[0].score, 0.70)

    def test_resolve_institution_auto_confirm(self):
        case = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="C-001",
            raw_institution_name="College of Engineering Pune",
            bureau=self.bureau_rb,
            status=CanonicalStatus.PENDING,
        )
        candidate = resolve_institution(case)
        self.assertIsNotNone(candidate)
        case.refresh_from_db()
        self.assertEqual(case.institution, self.inst_coep)
        self.assertIn(case.match_status, [InstitutionMatchStatus.CONFIRMED, InstitutionMatchStatus.EXACT_ID])

    def test_resolve_institution_fuzzy_review_queue(self):
        case = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="C-002",
            raw_institution_name="Col of Engg Pune",
            bureau=self.bureau_rb,
            status=CanonicalStatus.PENDING,
        )
        candidate = resolve_institution(case)
        case.refresh_from_db()
        if candidate and candidate.score >= 0.70:
            self.assertEqual(case.institution, self.inst_coep)
            self.assertEqual(case.match_status, InstitutionMatchStatus.FUZZY_SUGGESTED)

    def test_resolve_unmatched_cases_batch(self):
        ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="C-BATCH-1",
            raw_institution_name="Veermata Jijabai Technological Institute",
            bureau=self.bureau_rb,
            status=CanonicalStatus.PENDING,
        )
        ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="C-BATCH-2",
            raw_institution_name="Completely Non Existent Unknown School XYZ 999",
            bureau=self.bureau_pgrc,
            status=CanonicalStatus.PENDING,
        )
        stats = resolve_unmatched_cases()
        self.assertGreaterEqual(stats["resolved_auto"] + stats["suggested_review"], 1)
        self.assertGreaterEqual(stats["still_unmatched"], 1)


class Phase3OverlapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="officer_overlap", password="password123"
        )
        self.bureau_rb = BureauCell.objects.create(code="RB", name="Regulation Bureau")
        self.bureau_pgrc = BureauCell.objects.create(code="PGRC", name="Public Grievance Redressal Cell")

        self.inst = Institution.objects.create(
            name="Delhi Technological University",
            aicte_permanent_id="1-5001",
            district="New Delhi",
            state="Delhi",
        )

        self.case_rb = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="RB-01",
            case_number="RB-2026-001",
            institution=self.inst,
            bureau=self.bureau_rb,
            status=CanonicalStatus.UNDER_PROCESS,
        )
        self.case_pgrc = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="PGRC-01",
            case_number="PGRC-2026-001",
            institution=self.inst,
            bureau=self.bureau_pgrc,
            status=CanonicalStatus.PENDING,
        )

    def test_detect_overlaps_for_case(self):
        links = detect_overlaps_for_case(self.case_rb)
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.link_type, CaseLink.LinkType.OVERLAP)
        self.assertEqual(link.review_state, CaseLink.ReviewState.SUGGESTED)
        self.assertIn(self.case_rb, [link.case_a, link.case_b])
        self.assertIn(self.case_pgrc, [link.case_a, link.case_b])

    def test_no_overlap_if_case_disposed(self):
        self.case_pgrc.status = CanonicalStatus.DISPOSED
        self.case_pgrc.save()
        links = detect_overlaps_for_case(self.case_rb)
        self.assertEqual(len(links), 0)

    def test_run_full_overlap_scan(self):
        stats = run_full_overlap_scan()
        self.assertEqual(stats["institutions_scanned"], 1)
        self.assertEqual(stats["links_created"], 1)

    def test_review_overlap_decisions(self):
        links = detect_overlaps_for_case(self.case_rb)
        link = links[0]

        # Confirm decision
        review_overlap(link, "confirmed", user=self.user, note="Coordinating with PGRC")
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.CONFIRMED)
        self.assertEqual(link.decided_by, self.user)
        self.assertEqual(link.decision_note, "Coordinating with PGRC")

        # Related decision
        review_overlap(link, "related", user=self.user, note="Not an overlap, just related history")
        link.refresh_from_db()
        self.assertEqual(link.link_type, CaseLink.LinkType.RELATED)

        # Reject decision
        review_overlap(link, "rejected", user=self.user, note="Discarded false positive")
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.REJECTED)


class Phase3ViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.bureau_rb = BureauCell.objects.create(code="RB", name="Regulation Bureau")
        self.bureau_pgrc = BureauCell.objects.create(code="PGRC", name="Public Grievance Redressal Cell")

        self.inst = Institution.objects.create(
            name="Indian Institute of Science",
            aicte_permanent_id="1-9999",
            district="Bengaluru",
            state="Karnataka",
        )

        self.case1 = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="IIS-01",
            case_number="IIS-CASE-01",
            institution=self.inst,
            raw_institution_name="Indian Institute of Science",
            bureau=self.bureau_rb,
            status=CanonicalStatus.UNDER_PROCESS,
            match_status=InstitutionMatchStatus.EXACT_ID,
        )
        self.case2 = ComplaintCase.objects.create(
            source_system="DEMO",
            source_case_id="IIS-02",
            case_number="IIS-CASE-02",
            institution=self.inst,
            raw_institution_name="Indian Institute of Science",
            bureau=self.bureau_pgrc,
            status=CanonicalStatus.PENDING,
            match_status=InstitutionMatchStatus.FUZZY_SUGGESTED,
            match_confidence=0.82,
        )

        self.overlap_link = CaseLink.objects.create(
            case_a=self.case1,
            case_b=self.case2,
            link_type=CaseLink.LinkType.OVERLAP,
            review_state=CaseLink.ReviewState.SUGGESTED,
            explanation={"reason": "Planted test overlap"},
        )

    def test_case_list_view(self):
        response = self.client.get(reverse("complaints:case_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cross-Bureau Overlaps")
        self.assertContains(response, "Fuzzy Match Review")
        self.assertContains(response, "IIS-CASE-01")

    def test_case_detail_shows_overlap_banner(self):
        response = self.client.get(reverse("complaints:case_detail", kwargs={"pk": self.case1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cross-Bureau Overlap Detected")
        self.assertContains(response, "Compare &amp; Coordinate")

    def test_institution_detail_shows_multi_bureau_alert(self):
        response = self.client.get(reverse("complaints:institution_detail", kwargs={"pk": self.inst.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Multi-Bureau Overlap Detected")
        self.assertContains(response, "Review Overlap")

    def test_match_review_queue_view(self):
        response = self.client.get(reverse("complaints:match_review_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Match Review Queue")
        self.assertContains(response, "IIS-CASE-02")
        self.assertContains(response, "0.82")

    def test_match_review_confirm_action(self):
        url = reverse("complaints:match_review_action", kwargs={"pk": self.case2.pk})
        response = self.client.post(url, {"decision": "confirm"})
        self.assertEqual(response.status_code, 302)
        self.case2.refresh_from_db()
        self.assertEqual(self.case2.match_status, InstitutionMatchStatus.CONFIRMED)

    def test_match_review_reject_action(self):
        url = reverse("complaints:match_review_action", kwargs={"pk": self.case2.pk})
        response = self.client.post(url, {"decision": "reject"})
        self.assertEqual(response.status_code, 302)
        self.case2.refresh_from_db()
        self.assertEqual(self.case2.match_status, InstitutionMatchStatus.UNMATCHED)
        self.assertIsNone(self.case2.institution)

    def test_overlap_list_view(self):
        response = self.client.get(reverse("complaints:overlap_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cross-Bureau Overlap Cases")
        self.assertContains(response, "Review &amp; Compare")

    def test_overlap_detail_view_and_decision(self):
        url = reverse("complaints:overlap_detail", kwargs={"pk": self.overlap_link.pk})
        # GET side by side comparison
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Side-by-Side Comparison")
        self.assertContains(response, "IIS-CASE-01")
        self.assertContains(response, "IIS-CASE-02")

        # POST decision
        post_response = self.client.post(url, {
            "decision": "confirmed",
            "note": "Coordination meeting scheduled between RB and PGRC.",
        })
        self.assertEqual(post_response.status_code, 302)
        self.overlap_link.refresh_from_db()
        self.assertEqual(self.overlap_link.review_state, CaseLink.ReviewState.CONFIRMED)
        self.assertEqual(self.overlap_link.decision_note, "Coordination meeting scheduled between RB and PGRC.")
