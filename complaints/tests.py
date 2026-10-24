from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    AuditLog, BureauCell, CanonicalStatus, CaseLink, ComplaintCase,
    CoordinationMessage, CoordinationNotification, Institution,
    InstitutionMatchStatus,
)
from .services.overlap import sync_overlap_suggestions


class OverlapCenterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.reviewer = User.objects.create_user("reviewer", password="test-pass-123")
        self.pgrc_officer = User.objects.create_user("pgrc", password="test-pass-123")
        self.rb = BureauCell.objects.create(code="RB", name="Regional Bureau")
        self.pgrc = BureauCell.objects.create(code="PGRC", name="Public Grievance Cell")
        self.other = BureauCell.objects.create(code="ACADEMIC", name="Academic Cell")
        self.institution = Institution.objects.create(
            aicte_permanent_id="TEST-001", name="Example Institute", district="Pune", state="Maharashtra"
        )
        self.case_a = self.make_case("RB-1", self.rb, self.institution, "Facilities",
                                     "Laboratory safety inspection is pending.")
        self.case_b = self.make_case("PG-1", self.pgrc, self.institution, "Facilities",
                                     "Laboratory safety inspection is still pending.")
        self.case_same_bureau = self.make_case("RB-2", self.rb, self.institution, "Facilities", "Another open case.")
        self.grant("view_caselink", "review_case_links", "add_caselink", "add_coordinationmessage")
        self.client = Client()
        self.client.force_login(self.reviewer)

    def make_case(self, source_id, bureau, institution, category, description, **overrides):
        defaults = {
            "source_system": "TEST", "source_case_id": source_id,
            "case_number": source_id, "institution": institution,
            "raw_institution_name": institution.name if institution else "Unknown College",
            "match_status": InstitutionMatchStatus.EXACT_ID, "match_confidence": 1.0,
            "category": category, "description": description,
            "status": CanonicalStatus.PENDING, "bureau": bureau,
            "assigned_officer": f"Officer {bureau.code}", "next_action": "Review documents",
        }
        defaults.update(overrides)
        return ComplaintCase.objects.create(**defaults)

    def grant(self, *codenames):
        permissions = Permission.objects.filter(content_type__app_label="complaints", codename__in=codenames)
        self.reviewer.user_permissions.add(*permissions)

    def get_suggestion(self):
        sync_overlap_suggestions()
        return CaseLink.objects.get(case_a=self.case_a, case_b=self.case_b, link_type=CaseLink.LinkType.OVERLAP)

    def test_anonymous_users_cannot_open_overlap_center_or_post_decisions(self):
        link = self.get_suggestion()
        client = Client()
        response = client.get(reverse("complaints:overlap_center"))
        self.assertEqual(response.status_code, 302)
        response = client.post(reverse("complaints:decide_overlap", args=[link.pk]), {"decision": "confirm"})
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.SUGGESTED)

    def test_center_generates_only_cross_bureau_open_suggestions_and_shows_comparison(self):
        disposed = self.make_case("PG-closed", self.pgrc, self.institution, "Facilities",
                                  "Closed laboratory case.", status=CanonicalStatus.DISPOSED)
        response = self.client.get(reverse("complaints:overlap_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Overlap Center")
        self.assertContains(response, "Potential Overlapping Cases - Coordination Required")
        self.assertContains(response, self.case_a.case_number)
        self.assertContains(response, "Borderline institution matches")
        self.assertEqual(CaseLink.objects.filter(link_type=CaseLink.LinkType.OVERLAP).count(), 2)
        link = self.get_suggestion()
        dashboard = self.client.get(reverse("complaints:dashboard"))
        self.assertContains(dashboard, "Potential Overlapping Cases - Coordination Required")
        profile = self.client.get(reverse("complaints:institution_detail", args=[self.institution.pk]))
        self.assertContains(profile, "Potential Overlapping Cases - Coordination Required")
        comparison = self.client.get(reverse("complaints:overlap_detail", args=[link.pk]))
        self.assertEqual(comparison.status_code, 200)
        for text in ("Side-by-side case comparison", "Current owner", "Last action", "Next action", "Similarity highlights", "Potential Overlapping Cases"):
            if text == "Potential Overlapping Cases":
                continue
            self.assertContains(comparison, text)
        self.assertNotEqual(disposed.pk, self.case_a.pk)

    def test_confirm_reject_and_related_decisions_are_audited(self):
        link = self.get_suggestion()
        response = self.client.post(reverse("complaints:decide_overlap", args=[link.pk]),
                                    {"decision": "confirm", "reason": "Reviewed source records."})
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.CONFIRMED)
        self.assertEqual(link.decided_by, self.reviewer)
        self.assertIsNotNone(link.decided_at)
        self.assertEqual(link.decision_note, "Reviewed source records.")
        confirm_event = AuditLog.objects.get(action="overlap_confirmed", entity_id=str(link.pk))
        self.assertEqual(confirm_event.actor, self.reviewer)
        self.assertIsNotNone(confirm_event.occurred_at)
        self.assertEqual(confirm_event.entity_type, "CaseLink")
        self.assertEqual(confirm_event.details["reason"], "Reviewed source records.")

        another = self.make_case("PG-2", self.pgrc, self.institution, "Admissions", "Different matter.")
        link2 = CaseLink.objects.create(case_a=self.case_a, case_b=another,
                                        link_type=CaseLink.LinkType.OVERLAP)
        response = self.client.post(reverse("complaints:decide_overlap", args=[link2.pk]),
                                    {"decision": "reject", "reason": "Not the same matter."})
        self.assertEqual(response.status_code, 302)
        link2.refresh_from_db()
        self.assertEqual(link2.review_state, CaseLink.ReviewState.REJECTED)
        self.assertEqual(link2.decision_note, "Not the same matter.")
        rejection_events = AuditLog.objects.filter(action="overlap_rejected", entity_id=str(link2.pk))
        self.assertEqual(rejection_events.count(), 1)
        rejection_event = rejection_events.get()
        self.assertEqual(rejection_event.actor, self.reviewer)
        self.assertIsNotNone(rejection_event.occurred_at)
        self.assertEqual(rejection_event.details["reason"], "Not the same matter.")
        response = self.client.post(reverse("complaints:decide_overlap", args=[link2.pk]),
                                    {"decision": "reject", "reason": "Repeat stale form."})
        self.assertEqual(response.status_code, 302)
        link2.refresh_from_db()
        self.assertEqual(link2.review_state, CaseLink.ReviewState.REJECTED)
        self.assertEqual(link2.decision_note, "Not the same matter.")
        self.assertEqual(rejection_events.count(), 1)

        third = self.make_case("PG-3", self.pgrc, self.institution, "Admissions", "Another matter.")
        link3 = CaseLink.objects.create(case_a=self.case_a, case_b=third,
                                        link_type=CaseLink.LinkType.OVERLAP)
        response = self.client.post(reverse("complaints:decide_overlap", args=[link3.pk]),
                                    {"decision": "related", "reason": "Same underlying issue."})
        self.assertEqual(response.status_code, 302)
        link3.refresh_from_db()
        self.assertEqual(link3.link_type, CaseLink.LinkType.RELATED)
        self.assertEqual(link3.review_state, CaseLink.ReviewState.CONFIRMED)
        related_decided_at = link3.decided_at
        response = self.client.post(reverse("complaints:decide_overlap", args=[link3.pk]), {"decision": "reject"})
        self.assertEqual(response.status_code, 302)
        link3.refresh_from_db()
        self.assertEqual(link3.link_type, CaseLink.LinkType.RELATED)
        self.assertEqual(link3.review_state, CaseLink.ReviewState.CONFIRMED)
        self.assertEqual(link3.decided_at, related_decided_at)
        self.assertFalse(AuditLog.objects.filter(action="overlap_rejected", entity_id=str(link3.pk)).exists())
        related_event = AuditLog.objects.get(action="overlap_linked_as_related", entity_id=str(link3.pk))
        self.assertEqual(related_event.actor, self.reviewer)
        self.assertIsNotNone(related_event.occurred_at)
        self.assertEqual(related_event.details["reason"], "Same underlying issue.")

    def test_manual_link_and_unlink_preserve_audit_history(self):
        response = self.client.post(reverse("complaints:link_cases"),
                                    {"case_a": self.case_a.pk, "case_b": self.case_same_bureau.pk, "reason": "Shared source evidence."})
        link = CaseLink.objects.get(case_a=self.case_a, case_b=self.case_same_bureau,
                                   link_type=CaseLink.LinkType.RELATED)
        self.assertEqual(link.review_state, CaseLink.ReviewState.CONFIRMED)
        self.assertEqual(link.decided_by, self.reviewer)
        self.assertIsNotNone(link.decided_at)
        self.assertEqual(link.decision_note, "Shared source evidence.")
        self.assertEqual(response.status_code, 302)
        linked_event = AuditLog.objects.get(action="cases_manually_linked", entity_id=str(link.pk))
        self.assertEqual(linked_event.actor, self.reviewer)
        self.assertIsNotNone(linked_event.occurred_at)
        self.assertEqual(linked_event.details["reason"], "Shared source evidence.")
        response = self.client.post(reverse("complaints:unlink_cases", args=[link.pk]),
                                    {"reason": "Link no longer applies."})
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.REJECTED)
        self.assertEqual(link.decided_by, self.reviewer)
        self.assertIsNotNone(link.decided_at)
        self.assertEqual(link.decision_note, "Link no longer applies.")
        unlinked_event = AuditLog.objects.get(action="cases_manually_unlinked", entity_id=str(link.pk))
        self.assertEqual(unlinked_event.actor, self.reviewer)
        self.assertIsNotNone(unlinked_event.occurred_at)
        self.assertEqual(unlinked_event.details["reason"], "Link no longer applies.")
        self.assertEqual(AuditLog.objects.filter(action__in=["cases_manually_linked", "cases_manually_unlinked"]).count(), 2)

    def test_message_notifications_reach_only_the_mentioned_bureau(self):
        pgrc_group = Group.objects.create(name="bureau:PGRC")
        rb_group = Group.objects.create(name="bureau:RB")
        self.pgrc_officer.groups.add(pgrc_group)
        self.reviewer.groups.add(rb_group)
        self.rb_officer = get_user_model().objects.create_user("rb-officer", password="test-pass-123")
        self.rb_officer.groups.add(rb_group)
        view_permission = Permission.objects.get(content_type__app_label="complaints", codename="view_caselink")
        pgrc_group.permissions.add(view_permission)
        rb_group.permissions.add(view_permission)
        link = self.get_suggestion()
        response = self.client.post(reverse("complaints:post_coordination_message", args=[link.pk]),
                                    {"mentioned_bureau": self.pgrc.pk, "body": "Please review the matching dates."},
                                    follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "notifications created for 1 recipient")
        message = CoordinationMessage.objects.get(link=link)
        self.assertEqual(message.mentioned_bureau, self.pgrc)
        self.assertEqual(message.author, self.reviewer)
        self.assertIsNotNone(message.created_at)
        self.assertEqual(
            set(CoordinationNotification.objects.filter(message=message).values_list("recipient_id", flat=True)),
            {self.pgrc_officer.pk},
        )

        self.client.force_login(self.rb_officer)
        rb_inbox = self.client.get(reverse("complaints:coordination_notifications"))
        self.assertContains(rb_inbox, "0 unread")
        self.assertNotContains(rb_inbox, "Please review the matching dates.")

        self.client.force_login(self.pgrc_officer)
        inbox = self.client.get(reverse("complaints:coordination_notifications"))
        self.assertContains(inbox, "1 unread")
        self.assertContains(inbox, "Please review the matching dates.")
        notice = CoordinationNotification.objects.get(recipient=self.pgrc_officer, message=message)
        self.assertIsNotNone(notice.created_at)
        message_event = AuditLog.objects.get(action="coordination_message_posted", entity_id=str(link.pk))
        self.assertEqual(message_event.actor, self.reviewer)
        self.assertIsNotNone(message_event.occurred_at)
        self.assertEqual(message_event.details["message_id"], message.pk)
        self.assertEqual(message_event.details["mentioned_bureau"], self.pgrc.code)
        response = self.client.post(reverse("complaints:coordination_notifications"),
                                    {"notification_id": notice.pk})
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
        self.assertTrue(AuditLog.objects.filter(action="coordination_message_posted").exists())

    def test_message_warns_when_no_notification_recipient_is_assigned(self):
        link = self.get_suggestion()
        response = self.client.post(reverse("complaints:post_coordination_message", args=[link.pk]),
                                    {"mentioned_bureau": self.pgrc.pk, "body": "Synthetic no-recipient test."},
                                    follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no active notification recipients")
        message = CoordinationMessage.objects.get(body="Synthetic no-recipient test.")
        self.assertFalse(CoordinationNotification.objects.filter(message=message).exists())

    def test_missing_model_confidence_is_reported_as_unscored(self):
        institution = Institution.objects.create(name="Confidence Not Measured")
        first = self.make_case("NC-RB", self.rb, institution, "Policy", "Review a policy.",
                               match_status=InstitutionMatchStatus.CONFIRMED, match_confidence=None)
        second = self.make_case("NC-PG", self.pgrc, institution, "Policy", "Review a policy.",
                                match_status=InstitutionMatchStatus.CONFIRMED, match_confidence=None)
        sync_overlap_suggestions(institution_id=institution.pk)
        link = CaseLink.objects.get(case_a=first, case_b=second, link_type=CaseLink.LinkType.OVERLAP)
        self.assertIsNone(link.score)
        self.assertEqual(link.explanation["institution_confidence_display"], "Not scored")

    def test_borderline_match_confirmation_rechecks_overlap_candidates(self):
        corrected = Institution.objects.create(aicte_permanent_id="TEST-002", name="Correct Institute")
        other_case = self.make_case("SYNTHETIC-CORRECT-TARGET", self.other, corrected, "Safety", "A safety review.")
        borderline = self.make_case("SYNTHETIC-FUZZY-CORRECT", self.pgrc, self.institution, "Safety",
                                    "A safety review.", match_status=InstitutionMatchStatus.FUZZY_SUGGESTED,
                                    match_confidence=0.73)
        queue = self.client.get(reverse("complaints:overlap_center"))
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, "1 to review")
        self.assertContains(queue, "SYNTHETIC-FUZZY-CORRECT")
        self.assertFalse(CaseLink.objects.filter(
            Q(case_a=borderline, case_b=other_case) | Q(case_a=other_case, case_b=borderline),
            link_type=CaseLink.LinkType.OVERLAP).exists())
        response = self.client.post(reverse("complaints:review_institution_match", args=[borderline.pk]),
                                    {"institution_id": corrected.pk})
        self.assertEqual(response.status_code, 302)
        borderline.refresh_from_db()
        self.assertEqual(borderline.institution_id, corrected.pk)
        self.assertEqual(borderline.match_status, InstitutionMatchStatus.CONFIRMED)
        self.assertContains(self.client.get(reverse("complaints:overlap_center")), "0 to review")
        self.assertTrue(CaseLink.objects.filter(
            Q(case_a=borderline, case_b=other_case) | Q(case_a=other_case, case_b=borderline),
            link_type=CaseLink.LinkType.OVERLAP).exists())
        match_event = AuditLog.objects.get(action="institution_match_confirmed", entity_id=str(borderline.pk))
        self.assertEqual(match_event.actor, self.reviewer)
        self.assertIsNotNone(match_event.occurred_at)
        self.assertEqual(match_event.details["previous_institution_id"], self.institution.pk)
        self.assertEqual(match_event.details["institution_id"], corrected.pk)

    def test_borderline_match_can_confirm_the_suggested_institution(self):
        borderline = self.make_case(
            "SYNTHETIC-FUZZY-CONFIRM", self.pgrc, self.institution, "Facilities",
            "Confirm a suggested institution.",
            match_status=InstitutionMatchStatus.FUZZY_SUGGESTED,
            match_confidence=0.78,
        )
        queue = self.client.get(reverse("complaints:overlap_center"))
        self.assertContains(queue, "SYNTHETIC-FUZZY-CONFIRM")
        response = self.client.post(
            reverse("complaints:review_institution_match", args=[borderline.pk]),
            {"institution_id": self.institution.pk},
        )
        self.assertEqual(response.status_code, 302)
        borderline.refresh_from_db()
        self.assertEqual(borderline.institution_id, self.institution.pk)
        self.assertEqual(borderline.match_status, InstitutionMatchStatus.CONFIRMED)
        self.assertContains(self.client.get(reverse("complaints:overlap_center")), "0 to review")
        self.assertTrue(CaseLink.objects.filter(
            Q(case_a=borderline, case_b=self.case_a) | Q(case_a=self.case_a, case_b=borderline),
            link_type=CaseLink.LinkType.OVERLAP).exists())

    def test_authenticated_users_need_permissions_and_bureau_groups_limit_comparison_access(self):
        link = self.get_suggestion()
        unprivileged = get_user_model().objects.create_user("unprivileged", password="test-pass-123")
        self.client.force_login(unprivileged)
        self.assertEqual(self.client.get(reverse("complaints:overlap_center")).status_code, 403)
        self.client.force_login(self.reviewer)
        other_case = self.make_case("ACA-other", self.other, self.institution, "Safety", "Safety review.")
        outside_link = CaseLink.objects.create(case_a=self.case_b, case_b=other_case,
                                               link_type=CaseLink.LinkType.OVERLAP)
        rb_group = Group.objects.create(name="bureau:RB")
        self.reviewer.groups.add(rb_group)
        response = self.client.get(reverse("complaints:overlap_detail", args=[outside_link.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("complaints:overlap_detail", args=[link.pk]))
        self.assertEqual(response.status_code, 200)

    def test_audit_entries_are_append_only(self):
        event = AuditLog.objects.create(actor=self.reviewer, action="test_event",
                                        entity_type="CaseLink", entity_id="0")
        event.action = "changed_event"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=event.pk).update(action="changed_event")
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=event.pk).delete()
        event.refresh_from_db()
        self.assertEqual(event.action, "test_event")

    def test_change_actions_require_csrf(self):
        link = self.get_suggestion()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.reviewer)
        response = client.post(reverse("complaints:decide_overlap", args=[link.pk]),
                               {"decision": "confirm"})
        self.assertEqual(response.status_code, 403)
        link.refresh_from_db()
        self.assertEqual(link.review_state, CaseLink.ReviewState.SUGGESTED)

class LoginTemplateTests(TestCase):
    def test_login_page_renders_utf8_title(self):
        response = Client().get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in · Casework")
