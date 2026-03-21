# apps/recommendations/services.py
# Level 3 — Ingredient-Based Recommendation Engine

from django.db.models import Q
from apps.products.models import Product
from apps.skin_analysis.models import SkinAnalysis
from .models import Recommendation, RecommendationSession
import time

class RecommendationService:
    """
    Level 3 Ingredient-Based Recommendation Engine

    Algorithm:
    1. Filter products by skin type + age + gender
    2. Score by: skin_type(40%) + ingredient_match(30%) + age(20%) + gender(10%)
    3. Ingredient matching: check if product ingredients contain
       the key ingredients needed for that skin type
    4. Rank by score and return top N
    5. Generate ingredient-based reasoning for each product
    """

    # ── Scoring weights ───────────────────────────────────────
    WEIGHTS = {
        'skin_type':  0.40,  # 40% — most important
        'ingredient': 0.30,  # 30% — ingredient match (NEW)
        'age':        0.20,  # 20% — age group match
        'gender':     0.10,  # 10% — gender match
    }

    # ── Key ingredients per skin type ────────────────────────
    # Based on dermatological science:
    # Each skin type benefits from specific active ingredients.
    # Products containing these ingredients score higher.
    SKIN_INGREDIENTS = {
        'oily': [
            'salicylic acid', 'niacinamide', 'bha', 'zinc',
            'tea tree', 'clay', 'benzoyl peroxide', 'retinol',
            'glycolic acid', 'witch hazel', 'sulfur',
        ],
        'dry': [
            'hyaluronic acid', 'ceramide', 'shea butter',
            'glycerin', 'squalane', 'vitamin e', 'panthenol',
            'aloe vera', 'argan oil', 'rosehip', 'lanolin',
        ],
        'normal': [
            'vitamin c', 'niacinamide', 'peptide', 'retinol',
            'antioxidant', 'hyaluronic acid', 'green tea',
            'resveratrol', 'coenzyme q10', 'ferulic acid',
        ],
        'combination': [
            'niacinamide', 'hyaluronic acid', 'salicylic acid',
            'glycerin', 'ceramide', 'zinc', 'aloe vera',
        ],
        'sensitive': [
            'ceramide', 'aloe vera', 'centella', 'oat',
            'panthenol', 'allantoin', 'zinc oxide',
            'chamomile', 'green tea', 'glycerin',
        ],
    }

    # ── Step-level ingredient mapping ────────────────────────
    # Each routine step is linked to ingredient categories.
    # Used in frontend to match products to specific steps.
    STEP_INGREDIENTS = {
        'cleanse': [
            'salicylic acid', 'glycerin', 'ceramide',
            'tea tree', 'aloe vera', 'coconut',
        ],
        'tone': [
            'niacinamide', 'hyaluronic acid', 'witch hazel',
            'rose water', 'glycerin', 'aloe vera', 'zinc',
        ],
        'treat': [
            'retinol', 'vitamin c', 'niacinamide', 'bha',
            'aha', 'peptide', 'salicylic acid', 'glycolic acid',
            'benzoyl peroxide', 'azelaic acid',
        ],
        'moisturize': [
            'ceramide', 'hyaluronic acid', 'shea butter',
            'squalane', 'glycerin', 'peptide', 'vitamin e',
            'panthenol', 'argan oil',
        ],
        'protect': [
            'spf', 'zinc oxide', 'titanium dioxide',
            'sunscreen', 'uva', 'uvb',
        ],
    }

    @classmethod
    def get_recommendations(cls, skin_type, age, gender, limit=12):
        """
        Get ingredient-matched product recommendations.

        Args:
            skin_type: str — 'oily', 'dry', 'normal'
            age:       int
            gender:    str — 'male', 'female', 'other'
            limit:     int — number of results

        Returns:
            dict: recommendations, total_matched, processing_time_ms
        """
        start_time = time.time()

        # Step 1 — Base filter: available products only
        queryset = Product.objects.filter(is_available=True)

        # Step 2 — Skin type filter
        queryset = queryset.filter(
            Q(suitable_skin_type=skin_type) |
            Q(suitable_skin_type='all')
        )

        # Step 3 — Age range filter
        queryset = queryset.filter(
            min_age__lte=age,
            max_age__gte=age
        )

        # Step 4 — Gender filter
        queryset = queryset.filter(
            Q(gender=gender.lower()) |
            Q(gender='unisex')
        )

        # Step 5 — Score each product
        key_ingredients = cls.SKIN_INGREDIENTS.get(skin_type, cls.SKIN_INGREDIENTS['normal'])
        products_with_scores = []

        for product in queryset:
            match_data = cls._calculate_match_score(
                product, skin_type, age, gender, key_ingredients
            )
            products_with_scores.append({
                'product':           product,
                'match_score':       match_data['overall_score'],
                'skin_type_match':   match_data['skin_type_score'],
                'ingredient_match':  match_data['ingredient_score'],
                'age_match':         match_data['age_score'],
                'gender_match':      match_data['gender_score'],
                'matched_ingredients': match_data['matched_ingredients'],
                'reasoning':         match_data['reasoning'],
            })

        # Step 6 — Sort by score descending
        products_with_scores.sort(
            key=lambda x: x['match_score'],
            reverse=True
        )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            'recommendations':   products_with_scores[:limit],
            'total_matched':     len(products_with_scores),
            'processing_time_ms': processing_time,
        }

    @classmethod
    def _calculate_match_score(cls, product, skin_type, age, gender, key_ingredients):
        """
        Calculate ingredient-aware match score for a product.

        Scoring breakdown:
          skin_type_score  → 40%
          ingredient_score → 30% (NEW — checks product.ingredients field)
          age_score        → 20%
          gender_score     → 10%
        """

        # ── Skin type score ───────────────────────────────────
        if product.suitable_skin_type == skin_type:
            skin_score = 1.0
        elif product.suitable_skin_type == 'all':
            skin_score = 0.8
        else:
            skin_score = 0.3

        # ── Ingredient score ──────────────────────────────────
        # Check product.ingredients field (text) against
        # the key ingredients for this skin type.
        # More matches = higher score.
        product_ingredients_text = (product.ingredients or '').lower()
        matched_ingredients = []

        for ingredient in key_ingredients:
            if ingredient.lower() in product_ingredients_text:
                matched_ingredients.append(ingredient)

        if len(matched_ingredients) >= 3:
            ingredient_score = 1.0   # 3+ ingredients matched
        elif len(matched_ingredients) == 2:
            ingredient_score = 0.8   # 2 ingredients matched
        elif len(matched_ingredients) == 1:
            ingredient_score = 0.55  # 1 ingredient matched
        else:
            ingredient_score = 0.2   # no key ingredients found

        # ── Age score ─────────────────────────────────────────
        age_range = max(product.max_age - product.min_age, 1)
        age_mid   = (product.min_age + product.max_age) / 2
        age_diff  = abs(age - age_mid)
        age_score = max(0.0, 1.0 - (age_diff / age_range))

        # ── Gender score ──────────────────────────────────────
        if product.gender == gender.lower():
            gender_score = 1.0
        elif product.gender == 'unisex':
            gender_score = 0.9
        else:
            gender_score = 0.5

        # ── Weighted overall score ────────────────────────────
        overall_score = (
            skin_score       * cls.WEIGHTS['skin_type']  +
            ingredient_score * cls.WEIGHTS['ingredient'] +
            age_score        * cls.WEIGHTS['age']        +
            gender_score     * cls.WEIGHTS['gender']
        )

        reasoning = cls._generate_reasoning(
            product, skin_type, age, gender,
            skin_score, ingredient_score, age_score, gender_score,
            matched_ingredients
        )

        return {
            'overall_score':       round(overall_score, 3),
            'skin_type_score':     round(skin_score, 3),
            'ingredient_score':    round(ingredient_score, 3),
            'age_score':           round(age_score, 3),
            'gender_score':        round(gender_score, 3),
            'matched_ingredients': matched_ingredients,
            'reasoning':           reasoning,
        }

    @classmethod
    def _generate_reasoning(cls, product, skin_type, age, gender,
                            skin_score, ingredient_score, age_score,
                            gender_score, matched_ingredients):
        """
        Generate ingredient-aware human-readable reasoning.

        Example output:
        "Perfect for oily skin. Contains salicylic acid and niacinamide
         which are key ingredients for oily skin. Ideal for your age group."
        """
        reasons = []

        # Skin type reasoning
        if skin_score >= 0.9:
            reasons.append(f"Perfect for {skin_type} skin")
        elif skin_score >= 0.7:
            reasons.append(f"Great for {skin_type} skin")
        else:
            reasons.append(f"Suitable for {skin_type} skin")

        # Ingredient reasoning — the core of Level 3
        if len(matched_ingredients) >= 2:
            ingredient_list = ' and '.join(matched_ingredients[:2])
            reasons.append(
                f"Contains {ingredient_list} — key ingredients for {skin_type} skin"
            )
        elif len(matched_ingredients) == 1:
            reasons.append(
                f"Contains {matched_ingredients[0]} — beneficial for {skin_type} skin"
            )

        # Age reasoning
        if age_score >= 0.8:
            reasons.append(
                f"Ideal for your age group ({product.min_age}–{product.max_age})"
            )
        elif age_score >= 0.5:
            reasons.append(f"Suitable for ages {product.min_age}–{product.max_age}")

        # Bonus tags
        if product.discount_percent > 0:
            reasons.append(f"{product.discount_percent}% off")
        if product.is_featured:
            reasons.append("Featured product")

        return ". ".join(reasons) + "."

    @classmethod
    def get_products_for_step(cls, all_recommendations, step_key):
        """
        Filter recommendations for a specific routine step.
        Used by frontend to show matched products under each tip step.

        Args:
            all_recommendations: list from get_recommendations()
            step_key: str — 'cleanse', 'tone', 'treat', 'moisturize', 'protect'

        Returns:
            list: up to 2 best matched products for this step
        """
        step_ingredients = cls.STEP_INGREDIENTS.get(step_key, [])
        if not step_ingredients:
            return []

        matched = []
        for item in all_recommendations:
            product_text = (item['product'].ingredients or '').lower()
            for ing in step_ingredients:
                if ing.lower() in product_text:
                    matched.append(item)
                    break  # one match is enough per product

        return matched[:2]  # show max 2 products per step

    @classmethod
    def save_recommendations(cls, analysis_id, recommendation_data):
        """Save recommendations to database."""
        try:
            analysis = SkinAnalysis.objects.get(id=analysis_id)
        except SkinAnalysis.DoesNotExist:
            raise ValueError(f"Analysis {analysis_id} not found!")

        Recommendation.objects.filter(analysis=analysis).delete()

        session, _ = RecommendationSession.objects.update_or_create(
            analysis=analysis,
            defaults={
                'total_products_matched': recommendation_data['total_matched'],
                'algorithm_version':      'v2.0-ingredient-matching',
                'filters_applied': {
                    'skin_type': analysis.skin_type,
                    'age':       analysis.age,
                    'gender':    analysis.gender,
                },
                'processing_time_ms': recommendation_data['processing_time_ms'],
            }
        )

        saved = []
        for rank, item in enumerate(recommendation_data['recommendations'], start=1):
            rec = Recommendation.objects.create(
                analysis       = analysis,
                product        = item['product'],
                match_score    = item['match_score'],
                rank           = rank,
                skin_type_match= item['skin_type_match'],
                age_match      = item['age_match'],
                gender_match   = item['gender_match'],
                reasoning      = item['reasoning'],
            )
            saved.append(rec)

        return saved

    @classmethod
    def get_similar_products(cls, product_id, limit=6):
        """Get similar products by category, skin type, and price range."""
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Product.objects.none()

        price_min = product.price * 0.7
        price_max = product.price * 1.3

        return Product.objects.filter(
            category           = product.category,
            suitable_skin_type = product.suitable_skin_type,
            price__gte         = price_min,
            price__lte         = price_max,
            is_available       = True,
        ).exclude(id=product_id)[:limit]