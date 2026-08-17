import audit_ari_batch_a_safety_contract_repair as audit
import form_sender


def test_forensic_exact_targets():
    assert len(set(audit.CONFIRM3)) == 3
    assert len(set(audit.CHECKBOX2)) == 2
    assert len(set(audit.POST4)) == 4


def test_attempted_domains_are_not_submitted_by_audit():
    source = open(audit.__file__, encoding="utf-8").read()
    assert "submit_prepared_form" not in source
    assert "_click_submit" not in source
    assert '"post_requests": 0' in source


def test_confirmation_default_is_fail_closed():
    import inspect
    assert inspect.signature(form_sender._click_submit).parameters["allow_confirmation_final_submit"].default is False
    assert inspect.signature(form_sender.submit_prepared_form).parameters["allow_confirmation_final_submit"].default is False


def test_remaining_source_is_candidate_tail_only():
    source = open(audit.__file__, encoding="utf-8").read()
    assert "remaining = rows[10:]" in source
    assert "len(remaining) != 36" in source
