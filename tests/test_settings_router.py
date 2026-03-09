from datetime import date, timedelta


class TestGetSettings:
    async def test_returns_200_with_current_settings(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "global_start_date" in data
        assert "company_domains" in data
        assert "scoring_batch_size" in data
        assert "auto_score_after_fetch" in data
        assert data["global_start_date"] == "2025-09-01"
        assert data["company_domains"] == "nativecampusadvertising.com,native.fm"
        assert data["scoring_batch_size"] == 5
        assert data["auto_score_after_fetch"] is True


class TestPatchSettings:
    async def test_updates_global_start_date(self, client):
        resp = await client.patch(
            "/api/settings", json={"global_start_date": "2025-06-01"}
        )
        assert resp.status_code == 200
        assert resp.json()["global_start_date"] == "2025-06-01"

    async def test_updates_company_domains(self, client):
        resp = await client.patch(
            "/api/settings", json={"company_domains": "acme.com,test.com"}
        )
        assert resp.status_code == 200
        assert resp.json()["company_domains"] == "acme.com,test.com"

    async def test_updates_scoring_batch_size(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 10}
        )
        assert resp.status_code == 200
        assert resp.json()["scoring_batch_size"] == 10

    async def test_updates_auto_score_after_fetch(self, client):
        resp = await client.patch(
            "/api/settings", json={"auto_score_after_fetch": False}
        )
        assert resp.status_code == 200
        assert resp.json()["auto_score_after_fetch"] is False

    async def test_partial_update_leaves_other_fields_unchanged(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 20}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scoring_batch_size"] == 20
        assert data["global_start_date"] == "2025-09-01"
        assert data["company_domains"] == "nativecampusadvertising.com,native.fm"
        assert data["auto_score_after_fetch"] is True

    async def test_rejects_future_global_start_date(self, client):
        future = (date.today() + timedelta(days=30)).isoformat()
        resp = await client.patch(
            "/api/settings", json={"global_start_date": future}
        )
        assert resp.status_code == 422

    async def test_rejects_empty_company_domains(self, client):
        resp = await client.patch(
            "/api/settings", json={"company_domains": "  "}
        )
        assert resp.status_code == 422

    async def test_rejects_scoring_batch_size_less_than_1(self, client):
        resp = await client.patch(
            "/api/settings", json={"scoring_batch_size": 0}
        )
        assert resp.status_code == 422


class TestPatchWeights:
    async def test_updates_weight_value_proposition(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.25,
                "weight_personalisation": 0.25,
                "weight_cta": 0.25,
                "weight_clarity": 0.25,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["weight_value_proposition"] == 0.25

    async def test_rejects_weights_not_summing_to_one(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.50,
                "weight_personalisation": 0.30,
                "weight_cta": 0.20,
                "weight_clarity": 0.15,
            },
        )
        assert resp.status_code == 422

    async def test_accepts_weights_summing_to_one(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.40,
                "weight_personalisation": 0.30,
                "weight_cta": 0.20,
                "weight_clarity": 0.10,
            },
        )
        assert resp.status_code == 200


class TestPatchPrompts:
    async def test_updates_initial_email_prompt_blocks(self, client):
        blocks = {
            "opening": "Custom opening",
            "value_proposition": "Custom vp",
            "personalisation": "Custom pers",
            "cta": "Custom cta",
            "clarity": "Custom clarity",
            "closing": "Custom closing",
        }
        resp = await client.patch(
            "/api/settings",
            json={"initial_email_prompt_blocks": blocks},
        )
        assert resp.status_code == 200
        data = resp.json()["initial_email_prompt_blocks"]
        assert data["opening"] == "Custom opening"
        assert data["closing"] == "Custom closing"

    async def test_rejects_empty_block_value(self, client):
        blocks = {
            "opening": "  ",
            "value_proposition": "vp",
            "personalisation": "pers",
            "cta": "cta",
            "clarity": "clarity",
            "closing": "closing",
        }
        resp = await client.patch(
            "/api/settings",
            json={"initial_email_prompt_blocks": blocks},
        )
        assert resp.status_code == 422


class TestGetSettingsNewFields:
    async def test_response_includes_new_fields_with_defaults(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weight_value_proposition"] == 0.35
        assert data["weight_personalisation"] == 0.30
        assert data["weight_cta"] == 0.20
        assert data["weight_clarity"] == 0.15


class TestSettingsPage:
    async def test_returns_200_html(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_dev_mode_section_visible_when_auth_disabled(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Dev Mode" in resp.text

    async def test_dev_mode_contains_form_elements(self, client):
        resp = await client.get("/settings")
        html = resp.text
        assert 'id="fetch_start_date"' in html
        assert 'id="fetch_end_date"' in html
        assert 'id="fetch_max_count"' in html
        assert "Fetch Start Date" in html
        assert "Fetch End Date" in html
        assert "Max Emails" in html

    async def test_contains_general_tab(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "General" in resp.text

    async def test_contains_evaluation_tab(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Evaluation" in resp.text

    async def test_evaluation_tab_contains_weight_input(self, client):
        resp = await client.get("/settings?tab=evaluation")
        assert resp.status_code == 200
        assert 'name="weight_value_proposition"' in resp.text

    async def test_evaluation_tab_contains_block_textareas(self, client):
        resp = await client.get("/settings?tab=evaluation")
        html = resp.text
        assert 'id="initial_opening"' in html
        assert 'id="initial_value_proposition"' in html
        assert 'id="chain_email_opening"' in html
        assert 'id="chain_eval_opening"' in html
        assert 'id="chain_eval_progression"' in html

    async def test_evaluation_tab_contains_explainer_text(self, client):
        resp = await client.get("/settings?tab=evaluation")
        html = resp.text
        assert "cold outreach" in html.lower()
        assert "follow-up" in html.lower()
        assert "back-and-forth" in html.lower()

    async def test_no_reset_to_default_buttons(self, client):
        resp = await client.get("/settings?tab=evaluation")
        assert "Reset to Default" not in resp.text

    async def test_no_chain_statistics_section(self, client):
        resp = await client.get("/settings?tab=evaluation")
        assert "Chain Statistics" not in resp.text

    async def test_save_evaluation_settings_button(self, client):
        resp = await client.get("/settings?tab=evaluation")
        assert "Save Evaluation Settings" in resp.text


class TestPatchWeightsValidSums:
    async def test_accepts_weights_summing_to_one_point_zero(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.40,
                "weight_personalisation": 0.25,
                "weight_cta": 0.20,
                "weight_clarity": 0.15,
            },
        )
        assert resp.status_code == 200

    async def test_rejects_weights_summing_to_one_point_zero_five(self, client):
        resp = await client.patch(
            "/api/settings",
            json={
                "weight_value_proposition": 0.40,
                "weight_personalisation": 0.30,
                "weight_cta": 0.20,
                "weight_clarity": 0.15,
            },
        )
        assert resp.status_code == 422


class TestPatchPromptPersistence:
    async def test_initial_email_prompt_blocks_persist(self, client):
        blocks = {
            "opening": "Updated opening for testing",
            "value_proposition": "vp text",
            "personalisation": "pers text",
            "cta": "cta text",
            "clarity": "clarity text",
            "closing": "closing text",
        }
        resp = await client.patch(
            "/api/settings",
            json={"initial_email_prompt_blocks": blocks},
        )
        assert resp.status_code == 200
        assert resp.json()["initial_email_prompt_blocks"]["opening"] == "Updated opening for testing"

        get_resp = await client.get("/api/settings")
        assert get_resp.json()["initial_email_prompt_blocks"]["opening"] == "Updated opening for testing"

    async def test_chain_evaluation_prompt_blocks_persist(self, client):
        blocks = {
            "opening": "Updated chain eval opening",
            "progression": "prog text",
            "responsiveness": "resp text",
            "persistence": "pers text",
            "conversation_quality": "cq text",
            "closing": "closing text",
        }
        resp = await client.patch(
            "/api/settings",
            json={"chain_evaluation_prompt_blocks": blocks},
        )
        assert resp.status_code == 200
        assert resp.json()["chain_evaluation_prompt_blocks"]["opening"] == "Updated chain eval opening"

        get_resp = await client.get("/api/settings")
        assert get_resp.json()["chain_evaluation_prompt_blocks"]["opening"] == "Updated chain eval opening"


class TestSettingsDefaults:
    async def test_returns_default_prompt_blocks(self, client):
        resp = await client.get("/api/settings/defaults")
        assert resp.status_code == 200
        data = resp.json()
        assert "initial_email_prompt_blocks" in data
        assert "chain_email_prompt_blocks" in data
        assert "chain_evaluation_prompt_blocks" in data
        assert "opening" in data["initial_email_prompt_blocks"]
        assert "closing" in data["initial_email_prompt_blocks"]
        assert "value_proposition" in data["initial_email_prompt_blocks"]
        assert "progression" in data["chain_evaluation_prompt_blocks"]
