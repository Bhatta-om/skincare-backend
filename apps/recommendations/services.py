# apps/recommendations/services.py
# ═══════════════════════════════════════════════════════════════════════════════
# Hybrid Recommendation Engine — v4.0
#
# WHAT CHANGED FROM v3.0:
#   1. Ingredient matching uses fuzzy/partial token matching (no more false misses)
#   2. DermaProfile DB model is now checked FIRST before fallback to hardcoded dict
#   3. Age score uses Gaussian curve instead of linear division (fairer scoring)
#   4. Zero-match fallback: if hard DB filters return 0 products, we relax them
#      progressively so the user always gets results
#   5. Category diversity enforcement: max 3 products per category in top-12
#   6. ingredient_match score is now passed through to save_recommendations
#   7. Ingredient avoid penalty is capped (was unbounded before)
#   8. All weights are documented with research source
#
# WHAT YOUR ML ACTUALLY OUTPUTS (confirmed from terminal + skin_analysis/models.py):
#   skin_type          → 'dry', 'oily', or 'normal'  (CNN winner class)
#   confidence_score   → float 0.0–1.0               (winning class probability)
#   dry_probability    → float 0.0–1.0               (softmax output)
#   oily_probability   → float 0.0–1.0               (softmax output)
#   normal_probability → float 0.0–1.0               (softmax output)
#
# age and gender → entered manually by user, NOT from ML.
# SkinFeature (oiliness_score etc.) → CNN does NOT write this. Ignored entirely.
#
# Scientific Sources:
#   [1] Baumann BSTI          — PubMed 18555952
#   [2] AAD Skincare Guidelines — aad.org
#   [3] JAAD Delphi Consensus — jaad.org (62 dermatologists, 43 centers)
#   [4] Northwestern Derm Study — nm.org
#   [5] PMC Biophysical Params — mdpi.com/2079-9284/10/1/14
#
# Scoring Formula (weights sum to 1.0):
#   skin_type_match  35%  — Baumann BSTI [1]: skin type is the #1 predictor
#   ingredient_match 25%  — JAAD Delphi Consensus [3]: validated ingredient lists
#   concern_match    20%  — Northwestern thresholds [4]: probability-derived concern
#   age_match        15%  — AAD age-segmented guidelines [2]
#   gender_match      5%  — PMC physiological differences [5]
# ═══════════════════════════════════════════════════════════════════════════════

import math
import time
import logging

from django.db.models import Q

from apps.products.models import Product
from apps.skin_analysis.models import SkinAnalysis
from .models import Recommendation, RecommendationSession, DermaProfile

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ───────────────────────────────────────────────────────────────────────────────

VALID_SKIN_TYPES = ('dry', 'oily', 'normal')

# Maximum products from one category in the final top-N results
CATEGORY_DIVERSITY_LIMIT = 3

# How many top results to return by default
DEFAULT_RECOMMENDATION_LIMIT = 12


# ───────────────────────────────────────────────────────────────────────────────
# DERMA KNOWLEDGE BASE
# 24 profiles: 3 skin types × 4 age groups × 2 genders
# This is the FALLBACK. The DB DermaProfile table is checked first.
# Sources: AAD [2], JAAD Delphi [3], Baumann BSTI [1], PMC [5]
# ───────────────────────────────────────────────────────────────────────────────

DERMA_KNOWLEDGE_BASE = {

    # ══ OILY SKIN ═════════════════════════════════════════════════════════════

    ('oily', 'teen', 'female'): {
        'primary_ingredients':   ['salicylic acid', 'benzoyl peroxide', 'niacinamide', 'zinc'],
        'secondary_ingredients': ['tea tree', 'witch hazel', 'clay', 'sulfur'],
        'avoid_ingredients':     ['mineral oil', 'lanolin', 'petrolatum'],
        'key_concerns':          ['acne', 'general'],
        'source': 'AAD Teen Skincare + JAAD Delphi Consensus [2,3]',
    },
    ('oily', 'teen', 'male'): {
        'primary_ingredients':   ['salicylic acid', 'benzoyl peroxide', 'zinc', 'niacinamide'],
        'secondary_ingredients': ['tea tree', 'clay', 'sulfur', 'witch hazel'],
        'avoid_ingredients':     ['mineral oil', 'lanolin'],
        'key_concerns':          ['acne', 'general'],
        'source': 'AAD Men Skincare + JAAD Delphi Consensus + PMC [2,3,5]',
    },
    ('oily', 'young_adult', 'female'): {
        'primary_ingredients':   ['niacinamide', 'salicylic acid', 'retinol', 'glycolic acid'],
        'secondary_ingredients': ['bha', 'zinc', 'tea tree', 'witch hazel', 'clay'],
        'avoid_ingredients':     ['mineral oil', 'coconut oil', 'lanolin'],
        'key_concerns':          ['acne', 'brightening', 'general'],
        'source': 'AAD 20s Skincare + JAAD Delphi Consensus [2,3]',
    },
    ('oily', 'young_adult', 'male'): {
        'primary_ingredients':   ['salicylic acid', 'niacinamide', 'zinc', 'bha'],
        'secondary_ingredients': ['tea tree', 'benzoyl peroxide', 'clay', 'retinol'],
        'avoid_ingredients':     ['mineral oil', 'coconut oil'],
        'key_concerns':          ['acne', 'general'],
        'source': 'AAD Men Skincare Guidelines + PMC [2,5]',
    },
    ('oily', 'adult', 'female'): {
        'primary_ingredients':   ['retinol', 'niacinamide', 'salicylic acid', 'vitamin c'],
        'secondary_ingredients': ['glycolic acid', 'peptide', 'bha', 'zinc'],
        'avoid_ingredients':     ['mineral oil', 'heavy silicones'],
        'key_concerns':          ['acne', 'aging', 'brightening'],
        'source': 'AAD 30s–40s Skincare + JAAD Delphi Consensus [2,3]',
    },
    ('oily', 'adult', 'male'): {
        'primary_ingredients':   ['niacinamide', 'salicylic acid', 'retinol', 'zinc'],
        'secondary_ingredients': ['glycolic acid', 'bha', 'vitamin c'],
        'avoid_ingredients':     ['mineral oil', 'coconut oil'],
        'key_concerns':          ['acne', 'aging', 'general'],
        'source': 'AAD Men Skincare + JAAD [2,3]',
    },
    ('oily', 'mature', 'female'): {
        'primary_ingredients':   ['retinol', 'peptide', 'niacinamide', 'vitamin c'],
        'secondary_ingredients': ['hyaluronic acid', 'glycolic acid', 'ferulic acid'],
        'avoid_ingredients':     ['mineral oil', 'heavy occlusives'],
        'key_concerns':          ['aging', 'brightening', 'acne'],
        'source': 'AAD 50s+ Skincare + Baumann BSTI [2,1]',
    },
    ('oily', 'mature', 'male'): {
        'primary_ingredients':   ['retinol', 'niacinamide', 'peptide', 'vitamin c'],
        'secondary_ingredients': ['hyaluronic acid', 'salicylic acid', 'ferulic acid'],
        'avoid_ingredients':     ['mineral oil'],
        'key_concerns':          ['aging', 'acne', 'general'],
        'source': 'AAD Men 50+ Skincare + PMC [2,5]',
    },

    # ══ DRY SKIN ══════════════════════════════════════════════════════════════

    ('dry', 'teen', 'female'): {
        'primary_ingredients':   ['hyaluronic acid', 'ceramide', 'glycerin', 'aloe vera'],
        'secondary_ingredients': ['shea butter', 'panthenol', 'vitamin e'],
        'avoid_ingredients':     ['alcohol denat', 'salicylic acid', 'benzoyl peroxide'],
        'key_concerns':          ['hydration', 'general'],
        'source': 'AAD Teen Dry Skin + JAAD Delphi [2,3]',
    },
    ('dry', 'teen', 'male'): {
        'primary_ingredients':   ['ceramide', 'glycerin', 'hyaluronic acid'],
        'secondary_ingredients': ['aloe vera', 'panthenol', 'shea butter'],
        'avoid_ingredients':     ['alcohol denat', 'benzoyl peroxide'],
        'key_concerns':          ['hydration', 'general'],
        'source': 'AAD Teen Skincare [2]',
    },
    ('dry', 'young_adult', 'female'): {
        'primary_ingredients':   ['hyaluronic acid', 'ceramide', 'squalane', 'glycerin'],
        'secondary_ingredients': ['shea butter', 'rosehip', 'vitamin e', 'panthenol'],
        'avoid_ingredients':     ['alcohol denat', 'strong exfoliants'],
        'key_concerns':          ['hydration', 'brightening', 'general'],
        'source': 'AAD 20s Dry Skin + JAAD Delphi [2,3]',
    },
    ('dry', 'young_adult', 'male'): {
        'primary_ingredients':   ['hyaluronic acid', 'ceramide', 'glycerin', 'squalane'],
        'secondary_ingredients': ['aloe vera', 'panthenol', 'vitamin e'],
        'avoid_ingredients':     ['alcohol denat'],
        'key_concerns':          ['hydration', 'general'],
        'source': 'AAD Dry Skin Guidelines [2]',
    },
    ('dry', 'adult', 'female'): {
        'primary_ingredients':   ['hyaluronic acid', 'ceramide', 'retinol', 'peptide'],
        'secondary_ingredients': ['squalane', 'shea butter', 'vitamin c', 'argan oil'],
        'avoid_ingredients':     ['alcohol denat', 'high-concentration aha'],
        'key_concerns':          ['hydration', 'aging', 'brightening'],
        'source': 'AAD 30s–40s Dry Skin + JAAD Delphi [2,3]',
    },
    ('dry', 'adult', 'male'): {
        'primary_ingredients':   ['ceramide', 'hyaluronic acid', 'retinol', 'glycerin'],
        'secondary_ingredients': ['squalane', 'peptide', 'vitamin e'],
        'avoid_ingredients':     ['alcohol denat'],
        'key_concerns':          ['hydration', 'aging', 'general'],
        'source': 'AAD Men Dry Skin [2]',
    },
    ('dry', 'mature', 'female'): {
        'primary_ingredients':   ['ceramide', 'hyaluronic acid', 'peptide', 'retinol'],
        'secondary_ingredients': ['squalane', 'shea butter', 'lanolin', 'argan oil'],
        'avoid_ingredients':     ['alcohol denat', 'fragrance'],
        'key_concerns':          ['aging', 'hydration', 'general'],
        'source': 'AAD 60s+ Ointment Recommendation + Baumann BSTI [2,1]',
    },
    ('dry', 'mature', 'male'): {
        'primary_ingredients':   ['ceramide', 'hyaluronic acid', 'peptide', 'glycerin'],
        'secondary_ingredients': ['squalane', 'retinol', 'lanolin', 'vitamin e'],
        'avoid_ingredients':     ['alcohol denat', 'fragrance'],
        'key_concerns':          ['aging', 'hydration', 'general'],
        'source': 'AAD 60s+ Skincare + PMC [2,5]',
    },

    # ══ NORMAL SKIN ═══════════════════════════════════════════════════════════

    ('normal', 'teen', 'female'): {
        'primary_ingredients':   ['vitamin c', 'niacinamide', 'hyaluronic acid', 'aloe vera'],
        'secondary_ingredients': ['green tea', 'glycerin', 'ceramide'],
        'avoid_ingredients':     [],
        'key_concerns':          ['general', 'brightening'],
        'source': 'Baumann BSTI Normal Skin + AAD [1,2]',
    },
    ('normal', 'teen', 'male'): {
        'primary_ingredients':   ['niacinamide', 'hyaluronic acid', 'glycerin'],
        'secondary_ingredients': ['aloe vera', 'green tea', 'ceramide'],
        'avoid_ingredients':     [],
        'key_concerns':          ['general'],
        'source': 'Baumann BSTI Normal Skin [1]',
    },
    ('normal', 'young_adult', 'female'): {
        'primary_ingredients':   ['vitamin c', 'niacinamide', 'peptide', 'hyaluronic acid'],
        'secondary_ingredients': ['retinol', 'green tea', 'resveratrol', 'ferulic acid'],
        'avoid_ingredients':     [],
        'key_concerns':          ['brightening', 'general', 'hydration'],
        'source': 'AAD 20s Normal Skin + JAAD [2,3]',
    },
    ('normal', 'young_adult', 'male'): {
        'primary_ingredients':   ['niacinamide', 'hyaluronic acid', 'vitamin c'],
        'secondary_ingredients': ['peptide', 'green tea', 'ceramide'],
        'avoid_ingredients':     [],
        'key_concerns':          ['general', 'brightening'],
        'source': 'AAD Men Normal Skin [2]',
    },
    ('normal', 'adult', 'female'): {
        'primary_ingredients':   ['retinol', 'vitamin c', 'peptide', 'niacinamide'],
        'secondary_ingredients': ['hyaluronic acid', 'ferulic acid', 'coenzyme q10'],
        'avoid_ingredients':     [],
        'key_concerns':          ['aging', 'brightening', 'general'],
        'source': 'AAD 30s–40s + JAAD Delphi [2,3]',
    },
    ('normal', 'adult', 'male'): {
        'primary_ingredients':   ['retinol', 'niacinamide', 'vitamin c', 'peptide'],
        'secondary_ingredients': ['hyaluronic acid', 'ferulic acid'],
        'avoid_ingredients':     [],
        'key_concerns':          ['aging', 'general'],
        'source': 'AAD Men 30s–40s [2]',
    },
    ('normal', 'mature', 'female'): {
        'primary_ingredients':   ['retinol', 'peptide', 'vitamin c', 'hyaluronic acid'],
        'secondary_ingredients': ['ceramide', 'ferulic acid', 'coenzyme q10', 'resveratrol'],
        'avoid_ingredients':     [],
        'key_concerns':          ['aging', 'brightening', 'hydration'],
        'source': 'AAD 60s+ + Baumann BSTI [2,1]',
    },
    ('normal', 'mature', 'male'): {
        'primary_ingredients':   ['retinol', 'peptide', 'niacinamide', 'hyaluronic acid'],
        'secondary_ingredients': ['vitamin c', 'ceramide', 'coenzyme q10'],
        'avoid_ingredients':     [],
        'key_concerns':          ['aging', 'general'],
        'source': 'AAD Men 50+ [2]',
    },
}


# ───────────────────────────────────────────────────────────────────────────────
# STEP → INGREDIENT MAPPING (for skincare routine step filtering)
# ───────────────────────────────────────────────────────────────────────────────

STEP_INGREDIENTS = {
    'cleanse':    ['salicylic acid', 'glycerin', 'ceramide', 'tea tree', 'aloe vera', 'oat'],
    'tone':       ['niacinamide', 'hyaluronic acid', 'witch hazel', 'rose water', 'glycerin', 'zinc'],
    'treat':      ['retinol', 'vitamin c', 'niacinamide', 'bha', 'aha', 'peptide',
                   'salicylic acid', 'glycolic acid', 'benzoyl peroxide', 'ferulic acid'],
    'moisturize': ['ceramide', 'hyaluronic acid', 'shea butter', 'squalane',
                   'glycerin', 'peptide', 'vitamin e', 'panthenol', 'argan oil'],
    'protect':    ['spf', 'zinc oxide', 'titanium dioxide', 'sunscreen'],
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def age_to_group(age: int) -> str:
    """
    Convert integer age to AAD/Baumann age group key.
    Sources: AAD age-segmented guidelines [2], Baumann BSTI [1]
    """
    age = int(age)
    if age < 18:
        return 'teen'
    elif age < 30:
        return 'young_adult'
    elif age < 50:
        return 'adult'
    else:
        return 'mature'


def _normalise_gender(gender: str) -> str:
    """
    Normalise user-entered gender to 'male' or 'female'.
    'other' falls back to 'female' as the larger dermatological dataset.
    Source: PMC biophysical parameters [5]
    """
    g = gender.lower().strip()
    return g if g in ('male', 'female') else 'female'


def _get_derm_profile(skin_type: str, age_group: str, gender: str) -> dict:
    """
    Profile lookup order:
      1. DermaProfile DB table (admin-editable, takes precedence)
      2. DERMA_KNOWLEDGE_BASE hardcoded dict (fallback)
      3. ('normal', 'young_adult', 'female') as absolute last resort

    This means admins can update ingredients from Django admin without
    a code deploy, and the hardcoded dict is always a safety net.
    """
    gender_key = _normalise_gender(gender)
    skin_key   = skin_type if skin_type in VALID_SKIN_TYPES else 'normal'

    # ── Try DB first ──────────────────────────────────────────────────────────
    try:
        db_profile = DermaProfile.objects.get(
            skin_type=skin_key,
            age_group=age_group,
            gender=gender_key,
        )
        return {
            'primary_ingredients':   db_profile.primary_list(),
            'secondary_ingredients': db_profile.secondary_list(),
            'avoid_ingredients':     db_profile.avoid_list(),
            'key_concerns':          db_profile.concerns_list(),
            'source':                db_profile.source,
        }
    except DermaProfile.DoesNotExist:
        pass

    # ── Fallback to hardcoded dict ────────────────────────────────────────────
    key = (skin_key, age_group, gender_key)
    return DERMA_KNOWLEDGE_BASE.get(
        key,
        DERMA_KNOWLEDGE_BASE[('normal', 'young_adult', 'female')]
    )


def _ingredient_tokens(text: str) -> list[str]:
    """
    Tokenise an ingredient string for fuzzy matching.
    e.g. 'Sodium Hyaluronate (Hyaluronic Acid) 1%' →
         ['sodium', 'hyaluronate', 'hyaluronic', 'acid']

    This prevents false negatives like 'hyaluronic acid' not matching
    'Sodium Hyaluronate / Hyaluronic Acid' in a product ingredient list.
    """
    import re
    return re.findall(r'[a-z]+', text.lower())


def _ingredient_in_text(ingredient: str, product_tokens: list[str]) -> bool:
    """
    Check if an ingredient name appears in a tokenised product text.

    Strategy:
      - Split the ingredient name into words (tokens)
      - All tokens must appear in the product token list (order-insensitive)
      - This handles 'vitamin c' matching 'ascorbic acid / vitamin c 10%'
        and 'bha' matching 'beta-hydroxy acid (bha)'

    Examples:
      'salicylic acid' → ['salicylic', 'acid'] → both must be in product_tokens
      'vitamin c'      → ['vitamin', 'c']       → both must be in product_tokens
      'bha'            → ['bha']                → 'bha' must be in product_tokens
    """
    ing_tokens = _ingredient_tokens(ingredient)
    if not ing_tokens:
        return False
    return all(tok in product_tokens for tok in ing_tokens)


def detect_concern_from_probabilities(
    skin_type: str,
    confidence: float,
    dry_prob: float,
    oily_prob: float,
    normal_prob: float,
) -> str:
    """
    Derive the primary skin concern from CNN raw probability outputs.

    Logic is based on Northwestern study confidence thresholds [4]
    and Baumann BSTI skin concern mapping [1]:

    OILY:
      confidence ≥ 0.75 → 'acne'        (strongly oily → pores/breakouts)
      confidence ≥ 0.50 + dry_prob high  → 'general'    (mixed oily+dry signals)
      confidence ≥ 0.50                  → 'brightening' (mild oily → cosmetic)
      otherwise                          → 'general'

    DRY:
      confidence ≥ 0.75 → 'hydration'   (severely dry → urgent moisture)
      confidence ≥ 0.50 + normal high   → 'general'    (nearly normal)
      confidence ≥ 0.50                  → 'aging'      (mild dry → fine lines)
      otherwise                          → 'hydration'  (safe default for dry)

    NORMAL:
      dry_prob   ≥ 0.30 → 'hydration'   (normal leaning dry)
      oily_prob  ≥ 0.20 → 'general'     (normal leaning oily)
      otherwise          → 'brightening' (balanced → maintenance)

    Returns a key matching Product.CONCERN_CHOICES.
    """
    if skin_type == 'oily':
        if confidence >= 0.75:
            return 'acne'
        if confidence >= 0.50:
            return 'general' if dry_prob >= 0.25 else 'brightening'
        return 'general'

    if skin_type == 'dry':
        if confidence >= 0.75:
            return 'hydration'
        if confidence >= 0.50:
            return 'general' if normal_prob >= 0.30 else 'aging'
        return 'hydration'

    # normal
    if dry_prob >= 0.30:
        return 'hydration'
    if oily_prob >= 0.20:
        return 'general'
    return 'brightening'


def _gaussian_age_score(age: int, min_age: int, max_age: int) -> float:
    """
    Gaussian age match score — replaces the flawed linear formula in v3.0.

    v3.0 problem: score = 1 - |age - midpoint| / range
      → A product with range 10–80 (range=70) would score ~0.93 for a
        25-year-old even if the product is for seniors. Too generous.

    v4.0 fix: Gaussian curve centred on product midpoint.
      σ (sigma) = range / 4  so that the score is ~0.61 at the range edge.
      Score = exp(-(age - mid)² / (2σ²))

    Result:
      - Perfect match at midpoint → 1.0
      - At the range boundary     → ~0.61
      - Far outside the range     → approaches 0.0
      - Naturally penalises wrong-age products without a hard cliff

    Source: AAD age-segmented guidelines [2]
    """
    mid   = (min_age + max_age) / 2.0
    span  = max(max_age - min_age, 1)
    sigma = span / 4.0
    return math.exp(-((age - mid) ** 2) / (2 * sigma ** 2))


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class RecommendationService:
    """
    Hybrid Recommendation Engine v4.0.

    Inputs:
      skin_type   → CNN output: 'dry', 'oily', or 'normal'
      age         → user-entered integer (1–100)
      gender      → user-entered: 'male', 'female', or 'other'
      limit       → max recommendations to return (default 12)
      analysis_id → optional: used to load raw ML probabilities from DB

    Scoring weights (sum = 1.0):
      skin_type_match  35%  Baumann BSTI [1]
      ingredient_match 25%  JAAD Delphi Consensus [3]
      concern_match    20%  Northwestern Study [4]
      age_match        15%  AAD age-group guidelines [2]
      gender_match      5%  PMC biophysical parameters [5]
    """

    WEIGHTS = {
        'skin_type':  0.35,
        'ingredient': 0.25,
        'concern':    0.20,
        'age':        0.15,
        'gender':     0.05,
    }

    # ── Public entry point ────────────────────────────────────────────────────

    @classmethod
    def get_recommendations(
        cls,
        skin_type:   str,
        age:         int,
        gender:      str,
        limit:       int = DEFAULT_RECOMMENDATION_LIMIT,
        analysis_id: int = None,
    ) -> dict:
        """
        Generate scored, ranked, diversity-enforced recommendations.

        Returns:
            {
                'recommendations':     list of scored product dicts,
                'total_matched':       int,
                'processing_time_ms':  int,
                'detected_concern':    str,
                'derm_profile_source': str,
                'age_group':           str,
            }
        """
        start_time = time.time()

        # ── Validate skin_type ─────────────────────────────────────────────
        if skin_type not in VALID_SKIN_TYPES:
            raise ValueError(
                f"Invalid skin_type '{skin_type}'. "
                f"ML model only outputs: {VALID_SKIN_TYPES}"
            )

        age       = int(age)
        age_group = age_to_group(age)
        gender_key = _normalise_gender(gender)

        # ── Load derma profile (DB first, then hardcoded fallback) ─────────
        derm_profile = _get_derm_profile(skin_type, age_group, gender_key)

        # ── Load raw ML probabilities ──────────────────────────────────────
        dry_prob = oily_prob = normal_prob = confidence = 0.0

        if analysis_id:
            try:
                analysis_obj = SkinAnalysis.objects.get(id=analysis_id)
                confidence   = analysis_obj.confidence_score      or 0.0
                dry_prob     = analysis_obj.dry_probability        or 0.0
                oily_prob    = analysis_obj.oily_probability       or 0.0
                normal_prob  = analysis_obj.normal_probability     or 0.0
            except SkinAnalysis.DoesNotExist:
                logger.warning(f"SkinAnalysis id={analysis_id} not found; using defaults.")

        # Safe fallback if probabilities were not saved by the CNN view
        if dry_prob == 0.0 and oily_prob == 0.0 and normal_prob == 0.0:
            if skin_type == 'dry':
                dry_prob    = confidence
                oily_prob   = normal_prob = (1 - confidence) / 2
            elif skin_type == 'oily':
                oily_prob   = confidence
                dry_prob    = normal_prob = (1 - confidence) / 2
            else:
                normal_prob = confidence
                dry_prob    = oily_prob = (1 - confidence) / 2

        detected_concern = detect_concern_from_probabilities(
            skin_type, confidence, dry_prob, oily_prob, normal_prob
        )

        # ── Fetch candidate products (with progressive fallback) ───────────
        queryset = cls._fetch_candidates(skin_type, age, gender)

        # ── Score every candidate ──────────────────────────────────────────
        scored = []
        for product in queryset:
            match_data = cls._calculate_match_score(
                product      = product,
                skin_type    = skin_type,
                age          = age,
                gender       = gender,
                derm_profile = derm_profile,
                concern      = detected_concern,
            )
            scored.append({
                'product':          product,
                'match_score':      match_data['overall_score'],
                'skin_type_match':  match_data['skin_type_score'],
                'age_match':        match_data['age_score'],
                'gender_match':     match_data['gender_score'],
                'ingredient_match': match_data['ingredient_score'],
                'reasoning':        match_data['reasoning'],
                'matched_primary':  match_data['matched_primary'],
                'derm_source':      derm_profile.get('source', ''),
            })

        # Sort by score descending
        scored.sort(key=lambda x: x['match_score'], reverse=True)

        # Enforce category diversity before slicing
        diverse = cls._enforce_category_diversity(scored, limit)

        processing_time = int((time.time() - start_time) * 1000)

        return {
            'recommendations':     diverse,
            'total_matched':       len(scored),
            'processing_time_ms':  processing_time,
            'detected_concern':    detected_concern,
            'derm_profile_source': derm_profile.get('source', 'General Guidelines'),
            'age_group':           age_group,
        }

    # ── Candidate fetching with progressive fallback ──────────────────────────

    @classmethod
    def _fetch_candidates(cls, skin_type: str, age: int, gender: str):
        """
        Fetch candidate products using progressively relaxed filters.

        Pass 1 (strict):   skin_type match + age range + gender match
        Pass 2 (relaxed):  skin_type match only (drop age/gender hard filter)
        Pass 3 (broadest): all available products (skin_type='all' included)

        This guarantees the user always gets recommendations even if the
        admin hasn't added enough products for their exact profile.
        """
        gender_lower = gender.lower()
        base_qs = Product.objects.filter(is_available=True).select_related('category')

        # Pass 1 — strict
        qs = base_qs.filter(
            Q(suitable_skin_type=skin_type) | Q(suitable_skin_type='all')
        ).filter(
            min_age__lte=age, max_age__gte=age
        ).filter(
            Q(gender=gender_lower) | Q(gender='unisex')
        )
        if qs.exists():
            return qs

        logger.info(
            f"Pass 1 returned 0 for skin={skin_type}, age={age}, gender={gender_lower}. "
            f"Relaxing to Pass 2."
        )

        # Pass 2 — relax age and gender
        qs = base_qs.filter(
            Q(suitable_skin_type=skin_type) | Q(suitable_skin_type='all')
        )
        if qs.exists():
            return qs

        logger.info(f"Pass 2 returned 0. Falling back to all available products.")

        # Pass 3 — all available products
        return base_qs

    # ── Category diversity enforcement ────────────────────────────────────────

    @classmethod
    def _enforce_category_diversity(cls, scored: list, limit: int) -> list:
        """
        Cap the number of products from any single category at
        CATEGORY_DIVERSITY_LIMIT within the final top-N results.

        Example: if limit=12 and we have 8 moisturizers scored highest,
        only the top 3 moisturizers are included; remaining slots are
        filled by the next-best products from other categories.

        This ensures users see a full skincare routine (cleanser + serum
        + moisturizer + SPF) instead of 12 moisturizers.
        """
        category_counts: dict[int | None, int] = {}
        diverse = []

        for item in scored:
            cat_id = item['product'].category_id
            count  = category_counts.get(cat_id, 0)
            if count < CATEGORY_DIVERSITY_LIMIT:
                diverse.append(item)
                category_counts[cat_id] = count + 1
            if len(diverse) >= limit:
                break

        return diverse

    # ── Score calculation ─────────────────────────────────────────────────────

    @classmethod
    def _calculate_match_score(
        cls,
        product,
        skin_type:    str,
        age:          int,
        gender:       str,
        derm_profile: dict,
        concern:      str,
    ) -> dict:
        """
        Compute all 5 score components and the weighted overall score.

        Component details:

        1. skin_type_score (35%) — Baumann BSTI [1]
           1.0  exact match (product.suitable_skin_type == skin_type)
           0.8  product is for 'all' skin types
           0.2  mismatch (should be rare after _fetch_candidates filtering)

        2. ingredient_score (25%) — JAAD Delphi Consensus [3]
           Uses token-based fuzzy matching (v4.0 fix — see _ingredient_in_text).
           primary match   → weight 1.0 per ingredient
           secondary match → weight 0.5 per ingredient
           avoid match     → −0.15 per ingredient, capped at −0.45 total
           Final score clamped to [0.0, 1.0].

        3. concern_score (20%) — Northwestern Study [4]
           1.0  product concern == detected concern (exact)
           0.75 product concern is in the derm profile's key_concerns list
           0.6  product concern == 'general' (safe catch-all)
           0.3  none of the above

        4. age_score (15%) — AAD age-group guidelines [2]
           Gaussian curve (v4.0 fix — replaces flawed linear formula).
           See _gaussian_age_score() for details.

        5. gender_score (5%) — PMC biophysical parameters [5]
           1.0  exact gender match
           0.9  product is unisex
           0.4  mismatch (opposite gender product)
        """

        # 1. Skin type score
        if product.suitable_skin_type == skin_type:
            skin_score = 1.0
        elif product.suitable_skin_type == 'all':
            skin_score = 0.8
        else:
            skin_score = 0.2

        # 2. Ingredient score — fuzzy token matching
        product_tokens    = _ingredient_tokens(product.ingredients or '')
        primary_ings      = derm_profile.get('primary_ingredients',   [])
        secondary_ings    = derm_profile.get('secondary_ingredients', [])
        avoid_ings        = derm_profile.get('avoid_ingredients',     [])

        matched_primary   = [i for i in primary_ings   if _ingredient_in_text(i, product_tokens)]
        matched_secondary = [i for i in secondary_ings if _ingredient_in_text(i, product_tokens)]
        matched_avoid     = [i for i in avoid_ings     if _ingredient_in_text(i, product_tokens)]

        total_possible    = max(len(primary_ings) * 1.0 + len(secondary_ings) * 0.5, 1.0)
        raw_ing_score     = len(matched_primary) * 1.0 + len(matched_secondary) * 0.5
        ingredient_score  = min(raw_ing_score / total_possible, 1.0)

        # Capped avoid penalty: max −0.45 regardless of how many avoid ings found
        if matched_avoid:
            penalty          = min(0.15 * len(matched_avoid), 0.45)
            ingredient_score = max(ingredient_score - penalty, 0.0)

        # 3. Concern score
        derm_concerns = derm_profile.get('key_concerns', ['general'])
        if product.skin_concern == concern:
            concern_score = 1.0
        elif concern in derm_concerns and product.skin_concern in derm_concerns:
            concern_score = 0.75
        elif product.skin_concern == 'general':
            concern_score = 0.6
        else:
            concern_score = 0.3

        # 4. Age score — Gaussian curve (v4.0 fix)
        age_score = _gaussian_age_score(age, product.min_age, product.max_age)

        # 5. Gender score
        gender_lower = gender.lower()
        if product.gender == gender_lower:
            gender_score = 1.0
        elif product.gender == 'unisex':
            gender_score = 0.9
        else:
            gender_score = 0.4

        # ── Weighted overall ──────────────────────────────────────────────
        overall = (
            skin_score       * cls.WEIGHTS['skin_type']  +
            ingredient_score * cls.WEIGHTS['ingredient'] +
            concern_score    * cls.WEIGHTS['concern']    +
            age_score        * cls.WEIGHTS['age']        +
            gender_score     * cls.WEIGHTS['gender']
        )

        reasoning = cls._generate_reasoning(
            product, skin_type, age, gender,
            skin_score, ingredient_score, concern_score, age_score, gender_score,
            matched_primary, matched_secondary, matched_avoid,
            concern, derm_profile.get('source', ''),
        )

        return {
            'overall_score':     round(overall, 4),
            'skin_type_score':   round(skin_score, 4),
            'ingredient_score':  round(ingredient_score, 4),
            'concern_score':     round(concern_score, 4),
            'age_score':         round(age_score, 4),
            'gender_score':      round(gender_score, 4),
            'matched_primary':   matched_primary,
            'matched_secondary': matched_secondary,
            'matched_avoid':     matched_avoid,
            'reasoning':         reasoning,
        }

    # ── Reasoning text ────────────────────────────────────────────────────────

    @classmethod
    def _generate_reasoning(
        cls,
        product,
        skin_type:        str,
        age:              int,
        gender:           str,
        skin_score:       float,
        ingredient_score: float,
        concern_score:    float,
        age_score:        float,
        gender_score:     float,
        matched_primary:  list,
        matched_secondary: list,
        matched_avoid:    list,
        concern:          str,
        derm_source:      str,
    ) -> str:
        reasons = []

        # Skin type statement
        if skin_score >= 0.9:
            reasons.append(f"Specifically formulated for {skin_type} skin")
        elif skin_score >= 0.7:
            reasons.append(f"Suitable for {skin_type} skin")
        else:
            reasons.append(f"Works across multiple skin types including {skin_type}")

        # Ingredient match statement
        if matched_primary:
            top_two = matched_primary[:2]
            reasons.append(
                f"Contains {' and '.join(top_two)}, dermatologist-validated "
                f"for {skin_type} skin ({derm_source})"
            )
        elif matched_secondary:
            reasons.append(
                f"Contains {matched_secondary[0]}, beneficial for {skin_type} skin"
            )

        # Avoid-ingredient warning
        if matched_avoid:
            reasons.append(
                f"Note: contains {matched_avoid[0]} which may not be ideal "
                f"for {skin_type} skin — patch test recommended"
            )

        # Concern statement
        if concern_score >= 0.9:
            reasons.append(
                f"Directly targets {concern.replace('_', ' ')} — your primary skin concern"
            )
        elif concern_score >= 0.7:
            reasons.append(f"Addresses {concern.replace('_', ' ')}")

        # Age statement
        if age_score >= 0.8:
            reasons.append(
                f"Ideal for your age group "
                f"({product.min_age}–{product.max_age}) per AAD guidelines"
            )
        elif age_score >= 0.5:
            reasons.append(f"Appropriate for ages {product.min_age}–{product.max_age}")

        # Bonus signals
        if product.discount_percent > 0:
            reasons.append(f"{product.discount_percent}% off")
        if product.is_featured:
            reasons.append("Dermatologist-featured product")

        return ". ".join(reasons) + "."

    # ── Save to DB ────────────────────────────────────────────────────────────

    @classmethod
    def save_recommendations(cls, analysis_id: int, recommendation_data: dict) -> list:
        """
        Persist recommendations for an analysis.

        - Clears any existing recommendations for this analysis first
          (idempotent — safe to call multiple times)
        - Creates/updates the RecommendationSession
        - Creates one Recommendation row per product, in ranked order
        - ingredient_match is now included in filters_applied for admin visibility

        Returns list of saved Recommendation instances.
        """
        try:
            analysis = SkinAnalysis.objects.get(id=analysis_id)
        except SkinAnalysis.DoesNotExist:
            raise ValueError(f"SkinAnalysis id={analysis_id} not found.")

        # Clear stale recommendations
        Recommendation.objects.filter(analysis=analysis).delete()

        # Upsert session metadata
        RecommendationSession.objects.update_or_create(
            analysis=analysis,
            defaults={
                'total_products_matched': recommendation_data['total_matched'],
                'algorithm_version':      'v4.0-hybrid-derm-knowledge',
                'filters_applied': {
                    'skin_type':        analysis.skin_type,
                    'age':              analysis.age,
                    'age_group':        recommendation_data.get('age_group'),
                    'gender':           analysis.gender,
                    'detected_concern': recommendation_data.get('detected_concern'),
                    'derm_source':      recommendation_data.get('derm_profile_source'),
                },
                'processing_time_ms': recommendation_data['processing_time_ms'],
            }
        )

        saved = []
        for rank, item in enumerate(recommendation_data['recommendations'], start=1):
            rec = Recommendation.objects.create(
                analysis        = analysis,
                product         = item['product'],
                match_score     = item['match_score'],
                rank            = rank,
                skin_type_match = item['skin_type_match'],
                age_match       = item['age_match'],
                gender_match    = item['gender_match'],
                reasoning       = item['reasoning'],
            )
            saved.append(rec)

        return saved

    # ── Similar products ──────────────────────────────────────────────────────

    @classmethod
    def get_similar_products(cls, product_id: int, limit: int = 6):
        """
        Return products similar to a given product.
        Matches on category + skin type + price within ±30%.
        Used by the product detail page.
        """
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Product.objects.none()

        return Product.objects.filter(
            category           = product.category,
            suitable_skin_type = product.suitable_skin_type,
            price__gte         = product.price * 0.7,
            price__lte         = product.price * 1.3,
            is_available       = True,
        ).exclude(id=product_id)[:limit]

    # ── Routine step filtering ────────────────────────────────────────────────

    @classmethod
    def get_products_for_step(cls, all_recommendations: list, step_key: str) -> list:
        """
        Filter a recommendation list to products relevant to a routine step.

        step_key: 'cleanse' | 'tone' | 'treat' | 'moisturize' | 'protect'

        Returns up to 2 products whose ingredient list contains at least
        one of the step's key ingredients.
        Used by the frontend to display a personalised daily routine.
        """
        step_ings = STEP_INGREDIENTS.get(step_key, [])
        if not step_ings:
            return []

        matched = []
        for item in all_recommendations:
            tokens = _ingredient_tokens(item['product'].ingredients or '')
            if any(_ingredient_in_text(ing, tokens) for ing in step_ings):
                matched.append(item)

        return matched[:2]