"""
Regression tests for the deterministic compliance rule handlers.

Each handler in _DETERMINISTIC_FORMAT_HANDLERS must be tested with:
  1. A PASS case where the condition is not applicable (ingredient absent)
  2. A PASS case where the condition is met correctly
  3. A FAIL or WARNING case where the condition is violated

Run with:  pytest tests/test_compliance_handlers.py -v
"""
import sys
import os

# Allow imports from the project root without needing to install the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.services.compliance_engine import (
    CheckResult,
    _handle_swtnr_001,
    _handle_swtnr_002,
    _handle_swtnr_003,
    _handle_caff_001,
    _handle_glut_001,
    _handle_alrg_001,
    _handle_clm_brnd_001,
    _handle_clm_med_001,
    _handle_clm_comp_001,
    _handle_spt_lbl_001,
    _handle_spt_warn_001,
    _handle_fsmp_lbl_001,
    _handle_fsmp_lbl_002,
    _handle_fsmp_lbl_003,
    _handle_bot_lbl_001,
    _handle_bot_lbl_002,
    _handle_bot_warn_001,
    _handle_frt_warn_001,
    _handle_vgn_lbl_001,
    _handle_prob_lbl_001,
    _handle_nutra_novl_001,
    _handle_nutra_prebiotic_001,
    _handle_nutra_pif_001,
    _handle_fsmp_osm_001,
    calculate_compliance_score,
    _DETERMINISTIC_FORMAT_HANDLERS,
)


# ─── Helper ──────────────────────────────────────────────────────────────────

def _check(handler, extraction):
    """Call handler and return the CheckResult enum value."""
    result, actual, message = handler(extraction)
    return result


# ─── FSSAI-LBL-SWTNR-001: Aspartame → phenylketonuric warning ───────────────

class TestSwtnr001:
    def test_no_aspartame_passes(self):
        assert _check(_handle_swtnr_001, {"ingredient_list": ["sucrose", "maltodextrin"]}) == CheckResult.PASS

    def test_aspartame_with_warning_passes(self):
        assert _check(_handle_swtnr_001, {
            "ingredient_list": ["aspartame", "citric acid"],
            "warnings": ["Not recommended for phenylketonurics"],
        }) == CheckResult.PASS

    def test_aspartame_without_warning_fails(self):
        assert _check(_handle_swtnr_001, {
            "ingredient_list": ["aspartame"],
            "warnings": [],
        }) == CheckResult.FAIL

    def test_ins_951_alias_triggers_fail(self):
        assert _check(_handle_swtnr_001, {
            "ingredient_list": ["INS 951", "water"],
            "warnings": [],
        }) == CheckResult.FAIL

    def test_empty_extraction_passes(self):
        assert _check(_handle_swtnr_001, {}) == CheckResult.PASS


# ─── FSSAI-LBL-SWTNR-002: Non-caloric sweetener declaration ─────────────────

class TestSwtnr002:
    def test_no_sweeteners_passes(self):
        assert _check(_handle_swtnr_002, {"ingredient_list": ["glucose", "water"]}) == CheckResult.PASS

    def test_stevia_with_declaration_passes(self):
        assert _check(_handle_swtnr_002, {
            "ingredient_list": ["stevia"],
            "warnings": ["CONTAINS NON-CALORIC SWEETENER"],
        }) == CheckResult.PASS

    def test_stevia_without_declaration_fails(self):
        assert _check(_handle_swtnr_002, {
            "ingredient_list": ["stevia", "maltodextrin"],
            "warnings": [],
        }) == CheckResult.FAIL

    def test_sucralose_without_declaration_fails(self):
        assert _check(_handle_swtnr_002, {
            "ingredient_list": ["sucralose"],
            "health_claims": ["No added sugar"],
        }) == CheckResult.FAIL


# ─── FSSAI-LBL-SWTNR-003: Polyols → laxative warning ────────────────────────

class TestSwtnr003:
    def test_no_polyols_passes(self):
        assert _check(_handle_swtnr_003, {"ingredient_list": ["sucrose"]}) == CheckResult.PASS

    def test_xylitol_with_warning_passes(self):
        assert _check(_handle_swtnr_003, {
            "ingredient_list": ["xylitol"],
            "warnings": ["Excess consumption has a laxative effect"],
        }) == CheckResult.PASS

    def test_xylitol_without_warning_warns(self):
        assert _check(_handle_swtnr_003, {
            "ingredient_list": ["xylitol"],
            "warnings": [],
        }) == CheckResult.WARNING


# ─── FSSAI-LBL-CAFF-001: Caffeine declaration ────────────────────────────────

class TestCaff001:
    def test_no_caffeine_passes(self):
        assert _check(_handle_caff_001, {"ingredient_list": ["whey protein", "vitamin c"]}) == CheckResult.PASS

    def test_caffeine_with_declaration_passes(self):
        assert _check(_handle_caff_001, {
            "ingredient_list": ["caffeine anhydrous"],
            "warnings": ["CONTAINS CAFFEINE"],
        }) == CheckResult.PASS

    def test_guarana_without_declaration_fails(self):
        assert _check(_handle_caff_001, {
            "ingredient_list": ["guarana extract"],
            "warnings": [],
        }) == CheckResult.FAIL

    def test_green_tea_extract_triggers_fail(self):
        assert _check(_handle_caff_001, {
            "ingredient_list": ["green tea extract 50% EGCG"],
            "warnings": [],
        }) == CheckResult.FAIL


# ─── FSSAI-LBL-GLUT-001: Gluten Free claim integrity ────────────────────────

class TestGlut001:
    def test_no_claim_passes(self):
        assert _check(_handle_glut_001, {"ingredient_list": ["wheat flour"], "health_claims": []}) == CheckResult.PASS

    def test_gluten_free_claim_without_wheat_passes(self):
        assert _check(_handle_glut_001, {
            "health_claims": ["Gluten Free"],
            "ingredient_list": ["rice flour", "tapioca starch"],
        }) == CheckResult.PASS

    def test_gluten_free_claim_with_wheat_fails(self):
        assert _check(_handle_glut_001, {
            "health_claims": ["Gluten Free certified"],
            "ingredient_list": ["wheat starch", "vitamins"],
        }) == CheckResult.FAIL

    def test_gluten_free_in_product_name_triggers_check(self):
        # Product name contains "Gluten Free" (with space) — handler normalises to lowercase
        assert _check(_handle_glut_001, {
            "product_name": "Gluten Free Protein Bar",
            "ingredient_list": ["barley malt"],
            "health_claims": [],
        }) == CheckResult.FAIL


# ─── FSSAI-LBL-ALRG-001: Allergen declarations ───────────────────────────────

class TestAlrg001:
    def test_allergen_declared_passes(self):
        assert _check(_handle_alrg_001, {
            "ingredient_list": ["whey protein (milk)"],
            "allergen_declarations": ["Contains: Milk"],
        }) == CheckResult.PASS

    def test_no_allergens_no_declaration_passes(self):
        assert _check(_handle_alrg_001, {
            "ingredient_list": ["glucose syrup", "water"],
            "allergen_declarations": [],
        }) == CheckResult.PASS

    def test_milk_in_ingredients_no_declaration_warns(self):
        assert _check(_handle_alrg_001, {
            "ingredient_list": ["milk solids", "sugar"],
            "allergen_declarations": [],
        }) == CheckResult.WARNING

    def test_peanut_in_ingredients_warns(self):
        assert _check(_handle_alrg_001, {
            "ingredient_list": ["peanut oil"],
            "allergen_declarations": [],
        }) == CheckResult.WARNING


# ─── FSSAI-CLM-MED-001: No medical endorsement claims ───────────────────────

class TestClmMed001:
    def test_no_medical_claim_passes(self):
        assert _check(_handle_clm_med_001, {
            "health_claims": ["Supports bone health", "Rich in Vitamin D"],
        }) == CheckResult.PASS

    def test_recommended_by_doctor_fails(self):
        assert _check(_handle_clm_med_001, {
            "health_claims": ["Recommended by doctors across India"],
        }) == CheckResult.FAIL

    def test_doctor_approved_fails(self):
        assert _check(_handle_clm_med_001, {
            "health_claims": ["Doctor-approved formula"],
        }) == CheckResult.FAIL


# ─── FSSAI-CLM-COMP-001: No comparative/disparaging claims ──────────────────

class TestClmComp001:
    def test_no_comparative_claim_passes(self):
        assert _check(_handle_clm_comp_001, {
            "health_claims": ["High in protein", "Zero added sugar"],
        }) == CheckResult.PASS

    def test_unlike_other_brands_fails(self):
        assert _check(_handle_clm_comp_001, {
            "health_claims": ["Unlike other brands, we use no fillers"],
        }) == CheckResult.FAIL

    def test_better_than_fails(self):
        assert _check(_handle_clm_comp_001, {
            "health_claims": ["better than any other supplement on the market"],
        }) == CheckResult.FAIL


# ─── FSSAI-SPT-LBL-001: Sports product declaration ───────────────────────────

class TestSptLbl001:
    def test_sportsperson_declaration_present_passes(self):
        assert _check(_handle_spt_lbl_001, {
            "warnings": ["FOR SPORTSPERSON ONLY"],
        }) == CheckResult.PASS

    def test_missing_sportsperson_declaration_fails(self):
        assert _check(_handle_spt_lbl_001, {
            "warnings": ["Consult doctor before use"],
        }) == CheckResult.FAIL

    def test_in_product_type_declaration_passes(self):
        assert _check(_handle_spt_lbl_001, {
            "product_type_declaration": "Sports nutrition for sportsperson",
        }) == CheckResult.PASS


# ─── FSSAI-SPT-WARN-001: WADA prohibited substances ─────────────────────────

class TestSptWarn001:
    def test_clean_product_passes(self):
        assert _check(_handle_spt_warn_001, {
            "ingredient_list": ["creatine monohydrate", "beta-alanine"],
        }) == CheckResult.PASS

    def test_ephedrine_fails(self):
        assert _check(_handle_spt_warn_001, {
            "ingredient_list": ["ephedrine HCl 10mg"],
        }) == CheckResult.FAIL

    def test_dmaa_fails(self):
        assert _check(_handle_spt_warn_001, {
            "ingredient_list": ["DMAA", "caffeine"],
        }) == CheckResult.FAIL


# ─── FSSAI-FSMP-LBL-001/002/003: FSMP mandatory statements ──────────────────

class TestFsmpLbl:
    def test_fsmp_001_medical_advice_present_passes(self):
        assert _check(_handle_fsmp_lbl_001, {
            "warnings": ["To be used under medical advice only"],
        }) == CheckResult.PASS

    def test_fsmp_001_missing_fails(self):
        assert _check(_handle_fsmp_lbl_001, {"warnings": []}) == CheckResult.FAIL

    def test_fsmp_002_dietary_management_present_passes(self):
        assert _check(_handle_fsmp_lbl_002, {
            "warnings": ["For the dietary management of type 2 diabetes"],
        }) == CheckResult.PASS

    def test_fsmp_002_missing_fails(self):
        assert _check(_handle_fsmp_lbl_002, {"warnings": []}) == CheckResult.FAIL

    def test_fsmp_003_parenteral_warning_present_passes(self):
        assert _check(_handle_fsmp_lbl_003, {
            "warnings": ["NOT FOR PARENTERAL USE"],
        }) == CheckResult.PASS

    def test_fsmp_003_missing_fails(self):
        assert _check(_handle_fsmp_lbl_003, {"warnings": []}) == CheckResult.FAIL


# ─── FSSAI-BOT-LBL-001: Botanical scientific names ──────────────────────────

class TestBotLbl001:
    def test_no_herbs_passes(self):
        assert _check(_handle_bot_lbl_001, {
            "ingredient_list": ["whey protein", "vitamin c"],
        }) == CheckResult.PASS

    def test_herb_with_latin_name_passes(self):
        assert _check(_handle_bot_lbl_001, {
            "ingredient_list": ["Ashwagandha (Withania somnifera) extract"],
        }) == CheckResult.PASS

    def test_herb_without_latin_name_warns(self):
        assert _check(_handle_bot_lbl_001, {
            "ingredient_list": ["ashwagandha root extract 500mg"],
        }) == CheckResult.WARNING


# ─── FSSAI-BOT-LBL-002: Extract ratio declaration ───────────────────────────

class TestBotLbl002:
    def test_no_extract_passes(self):
        assert _check(_handle_bot_lbl_002, {
            "ingredient_list": ["ashwagandha root powder"],
        }) == CheckResult.PASS

    def test_extract_with_ratio_passes(self):
        assert _check(_handle_bot_lbl_002, {
            "ingredient_list": ["ashwagandha extract 10:1"],
        }) == CheckResult.PASS

    def test_extract_with_standardization_passes(self):
        assert _check(_handle_bot_lbl_002, {
            "ingredient_list": ["turmeric extract standardized to 95% curcuminoids"],
        }) == CheckResult.PASS

    def test_extract_without_ratio_warns(self):
        assert _check(_handle_bot_lbl_002, {
            "ingredient_list": ["bacopa extract", "brahmi extract"],
        }) == CheckResult.WARNING


# ─── FSSAI-BOT-WARN-001: Contraindication herbs ─────────────────────────────

class TestBotWarn001:
    def test_no_contra_herbs_passes(self):
        assert _check(_handle_bot_warn_001, {
            "ingredient_list": ["turmeric", "ginger"],
        }) == CheckResult.PASS

    def test_fenugreek_with_warning_passes(self):
        assert _check(_handle_bot_warn_001, {
            "ingredient_list": ["fenugreek seed extract"],
            "warnings": ["Not recommended during pregnancy or lactation"],
        }) == CheckResult.PASS

    def test_fenugreek_without_warning_warns(self):
        assert _check(_handle_bot_warn_001, {
            "ingredient_list": ["fenugreek extract 300mg"],
            "warnings": ["Consult doctor"],
        }) == CheckResult.WARNING


# ─── FSSAI-FRT-WARN-001: Iron fortification advisory ────────────────────────

class TestFrtWarn001:
    def test_non_fortified_passes(self):
        assert _check(_handle_frt_warn_001, {
            "health_claims": ["Rich in Vitamin C"],
            "ingredient_list": ["ascorbic acid"],
        }) == CheckResult.PASS

    def test_iron_fortified_with_thalassemia_advisory_passes(self):
        assert _check(_handle_frt_warn_001, {
            "health_claims": ["Iron Fortified — supports healthy blood"],
            "warnings": ["People with thalassemia may consume under medical supervision"],
            "ingredient_list": ["ferrous sulphate"],
        }) == CheckResult.PASS

    def test_iron_fortified_without_advisory_fails(self):
        assert _check(_handle_frt_warn_001, {
            "health_claims": ["Fortified with Iron"],
            "warnings": [],
            "ingredient_list": ["ferrous fumarate"],
        }) == CheckResult.FAIL


# ─── FSSAI-VGN-LBL-001: Vegan claim → FSSAI vegan logo ─────────────────────

class TestVgnLbl001:
    def test_no_vegan_claim_passes(self):
        assert _check(_handle_vgn_lbl_001, {
            "health_claims": ["Whey protein concentrate"],
        }) == CheckResult.PASS

    def test_vegan_claim_with_logo_passes(self):
        assert _check(_handle_vgn_lbl_001, {
            "health_claims": ["100% Vegan"],
            "veg_nonveg_mark": "VEGAN",
        }) == CheckResult.PASS

    def test_vegan_claim_without_logo_warns(self):
        assert _check(_handle_vgn_lbl_001, {
            "health_claims": ["Vegan certified"],
            "veg_nonveg_mark": "GREEN",
        }) == CheckResult.WARNING

    def test_vegan_claim_no_mark_warns(self):
        assert _check(_handle_vgn_lbl_001, {
            "health_claims": ["Suitable for vegans"],
        }) == CheckResult.WARNING


# ─── FSSAI-PROB-LBL-001: Probiotic CFU count ─────────────────────────────────

class TestProbLbl001:
    def test_no_probiotic_passes(self):
        assert _check(_handle_prob_lbl_001, {
            "ingredient_list": ["maltodextrin", "vitamin c"],
        }) == CheckResult.PASS

    def test_probiotic_with_cfu_passes(self):
        assert _check(_handle_prob_lbl_001, {
            "ingredient_list": ["Lactobacillus acidophilus 10 Billion CFU"],
            "health_claims": [],
        }) == CheckResult.PASS

    def test_probiotic_without_cfu_fails(self):
        assert _check(_handle_prob_lbl_001, {
            "ingredient_list": ["Lactobacillus rhamnosus", "Bifidobacterium longum"],
            "health_claims": ["Supports gut health"],
        }) == CheckResult.FAIL

    def test_probiotic_in_claims_without_cfu_fails(self):
        assert _check(_handle_prob_lbl_001, {
            "ingredient_list": ["inulin"],
            "health_claims": ["Contains live probiotic cultures"],
        }) == CheckResult.FAIL


# ─── FSSAI-NUTRA-NOVL-001: Novel food prior approval ────────────────────────

class TestNutraNovl001:
    def test_not_novel_food_passes(self):
        assert _check(_handle_nutra_novl_001, {
            "product_type_declaration": "Health Supplement",
        }) == CheckResult.PASS

    def test_novel_food_with_approval_ref_passes(self):
        assert _check(_handle_nutra_novl_001, {
            "product_type_declaration": "Novel Food",
            "warnings": ["FSSAI Approval No. NOVEL/2024/001"],
        }) == CheckResult.PASS

    def test_novel_food_without_approval_fails(self):
        assert _check(_handle_nutra_novl_001, {
            "product_type_declaration": "Novel Food",
            "warnings": ["Keep out of reach of children"],
        }) == CheckResult.FAIL


# ─── FSSAI-NUTRA-PREBIOTIC-001: Prebiotic with effective dose ───────────────

class TestNutraPrebiotic001:
    def test_no_prebiotic_passes(self):
        assert _check(_handle_nutra_prebiotic_001, {
            "ingredient_list": ["whey protein", "vitamin b12"],
        }) == CheckResult.PASS

    def test_inulin_with_dose_passes(self):
        assert _check(_handle_nutra_prebiotic_001, {
            "ingredient_list": ["inulin 5g", "oat fibre"],
        }) == CheckResult.PASS

    def test_fos_without_dose_warns(self):
        assert _check(_handle_nutra_prebiotic_001, {
            "ingredient_list": ["FOS (fructo-oligosaccharide)", "pectin"],
        }) == CheckResult.WARNING


# ─── FSSAI-NUTRA-PIF-001: Product Information File for botanicals ────────────

class TestNutraPif001:
    def test_no_botanicals_passes(self):
        assert _check(_handle_nutra_pif_001, {
            "ingredient_list": ["creatine monohydrate", "taurine"],
        }) == CheckResult.PASS

    def test_botanical_with_pif_reference_passes(self):
        assert _check(_handle_nutra_pif_001, {
            "ingredient_list": ["ashwagandha extract"],
            "warnings": ["Product Information File available with manufacturer"],
        }) == CheckResult.PASS

    def test_botanical_without_pif_warns(self):
        assert _check(_handle_nutra_pif_001, {
            "ingredient_list": ["ashwagandha root", "turmeric extract"],
            "warnings": ["Consult doctor"],
        }) == CheckResult.WARNING


# ─── FSSAI-FSMP-OSM-001: FSMP osmolality declaration ────────────────────────

class TestFsmpOsm001:
    def test_osmolality_present_passes(self):
        assert _check(_handle_fsmp_osm_001, {
            "nutrition_facts": "Osmolality: 300 mOsm/kg",
        }) == CheckResult.PASS

    def test_osmolarity_keyword_passes(self):
        assert _check(_handle_fsmp_osm_001, {
            "warnings": ["Osmolarity 250 mOsm/L"],
        }) == CheckResult.PASS

    def test_mosm_keyword_passes(self):
        assert _check(_handle_fsmp_osm_001, {
            "notes": "290 mOsm/kg water",
        }) == CheckResult.PASS

    def test_missing_osmolality_fails(self):
        assert _check(_handle_fsmp_osm_001, {
            "warnings": ["For the dietary management of malnutrition"],
        }) == CheckResult.FAIL


# ─── Registry completeness check ─────────────────────────────────────────────

def test_all_registered_handlers_are_callable():
    """Every entry in the registry must be a callable."""
    for code, handler in _DETERMINISTIC_FORMAT_HANDLERS.items():
        assert callable(handler), f"{code} handler is not callable"


def test_all_registered_handlers_return_3_tuple():
    """Every handler must return a (CheckResult, str|None, str) tuple on an empty extraction."""
    for code, handler in _DETERMINISTIC_FORMAT_HANDLERS.items():
        result = handler({})
        assert isinstance(result, tuple), f"{code} did not return a tuple"
        assert len(result) == 3, f"{code} tuple length != 3"
        assert isinstance(result[0], CheckResult), f"{code} first element is not CheckResult"


# ─── Scoring tests ────────────────────────────────────────────────────────────

class TestComplianceScore:
    """Tests for the penalty-based calculate_compliance_score function."""

    def test_empty_checks_returns_zero(self):
        assert calculate_compliance_score([]) == 0

    def test_all_pass_returns_100(self):
        """No failures → score must be 100."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        checks = []
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            c = MagicMock()
            c.result = CR.PASS
            c.rule = MagicMock()
            c.rule.severity = sev
            checks.append(c)
        assert calculate_compliance_score(checks) == 100

    def test_two_critical_failures_score_80(self):
        """2 CRITICAL failures → 100 - (2×10) = 80."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        checks = []
        for _ in range(2):
            c = MagicMock()
            c.result = CR.FAIL
            c.rule = MagicMock()
            c.rule.severity = Severity.CRITICAL
            checks.append(c)
        assert calculate_compliance_score(checks) == 80

    def test_three_high_failures_score_82(self):
        """3 HIGH failures → 100 - (3×6) = 82."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        checks = []
        for _ in range(3):
            c = MagicMock()
            c.result = CR.FAIL
            c.rule = MagicMock()
            c.rule.severity = Severity.HIGH
            checks.append(c)
        assert calculate_compliance_score(checks) == 82

    def test_warning_is_half_penalty(self):
        """1 CRITICAL warning → 100 - (0.5×10) = 95."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        c = MagicMock()
        c.result = CR.WARNING
        c.rule = MagicMock()
        c.rule.severity = Severity.CRITICAL
        assert calculate_compliance_score([c]) == 95

    def test_score_never_below_zero(self):
        """Many failures must not produce a negative score."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        checks = []
        for _ in range(20):
            c = MagicMock()
            c.result = CR.FAIL
            c.rule = MagicMock()
            c.rule.severity = Severity.CRITICAL
            checks.append(c)
        assert calculate_compliance_score(checks) == 0

    def test_skipped_checks_not_penalised(self):
        """SKIPPED results must not affect the score."""
        from unittest.mock import MagicMock
        from app.models import CheckResult as CR, Severity
        checks = []
        for _ in range(5):
            c = MagicMock()
            c.result = CR.SKIPPED
            c.rule = MagicMock()
            c.rule.severity = Severity.CRITICAL
            checks.append(c)
        assert calculate_compliance_score(checks) == 100
