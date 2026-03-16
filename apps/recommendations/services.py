# apps/recommendations/services.py

from django.db.models import Q
from apps.products.models import Product
from apps.skin_analysis.models import SkinAnalysis
from .models import Recommendation, RecommendationSession
import time

class RecommendationService:
    """
    Product Recommendation Engine
    
    Algorithm:
    1. Filter products by skin type
    2. Filter by age range
    3. Filter by gender
    4. Calculate match scores
    5. Rank by score
    6. Return top N products
    """
    
    # Weights for match scoring
    WEIGHTS = {
        'skin_type': 0.5,   # 50% weight — most important
        'age': 0.3,         # 30% weight
        'gender': 0.2,      # 20% weight
    }
    
    @classmethod
    def get_recommendations(cls, skin_type, age, gender, limit=12):
        """
        Get product recommendations
        
        Args:
            skin_type: str — 'oily', 'dry', 'normal', 'combination'
            age: int
            gender: str — 'male', 'female', 'other'
            limit: int — number of recommendations
        
        Returns:
            list: Recommended products with scores
        """
        
        start_time = time.time()
        
        # Step 1: Base filter — available products only
        queryset = Product.objects.filter(is_available=True)
        
        # Step 2: Skin type filter
        queryset = queryset.filter(
            Q(suitable_skin_type=skin_type) | 
            Q(suitable_skin_type='all')
        )
        
        # Step 3: Age range filter
        queryset = queryset.filter(
            min_age__lte=age,
            max_age__gte=age
        )
        
        # Step 4: Gender filter
        queryset = queryset.filter(
            Q(gender=gender.lower()) | 
            Q(gender='unisex')
        )
        
        # Step 5: Calculate match scores
        products_with_scores = []
        
        for product in queryset:
            match_data = cls._calculate_match_score(
                product, skin_type, age, gender
            )
            
            products_with_scores.append({
                'product': product,
                'match_score': match_data['overall_score'],
                'skin_type_match': match_data['skin_type_score'],
                'age_match': match_data['age_score'],
                'gender_match': match_data['gender_score'],
                'reasoning': match_data['reasoning'],
            })
        
        # Step 6: Sort by match score (highest first)
        products_with_scores.sort(
            key=lambda x: x['match_score'],
            reverse=True
        )
        
        # Step 7: Limit results
        top_recommendations = products_with_scores[:limit]
        
        # Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)  # ms
        
        return {
            'recommendations': top_recommendations,
            'total_matched': len(products_with_scores),
            'processing_time_ms': processing_time,
        }
    
    @classmethod
    def _calculate_match_score(cls, product, skin_type, age, gender):
        """
        Calculate match score for a product
        
        Scoring:
        - Skin type match: 0.0 - 1.0
        - Age match: 0.0 - 1.0
        - Gender match: 0.0 - 1.0
        
        Overall = weighted average
        
        Returns:
            dict: Match scores & reasoning
        """
        
        # Skin type score
        if product.suitable_skin_type == skin_type:
            skin_score = 1.0
        elif product.suitable_skin_type == 'all':
            skin_score = 0.8
        else:
            skin_score = 0.3  # Partial match (combination skin)
        
        # Age score (how close to optimal range)
        age_range = product.max_age - product.min_age
        age_mid = (product.min_age + product.max_age) / 2
        age_diff = abs(age - age_mid)
        age_score = max(0.0, 1.0 - (age_diff / age_range))
        
        # Gender score
        if product.gender == gender.lower():
            gender_score = 1.0
        elif product.gender == 'unisex':
            gender_score = 0.9
        else:
            gender_score = 0.5  # Can still use opposite gender products
        
        # Overall weighted score
        overall_score = (
            skin_score * cls.WEIGHTS['skin_type'] +
            age_score * cls.WEIGHTS['age'] +
            gender_score * cls.WEIGHTS['gender']
        )
        
        # Generate reasoning
        reasoning = cls._generate_reasoning(
            product, skin_type, age, gender,
            skin_score, age_score, gender_score
        )
        
        return {
            'overall_score': round(overall_score, 3),
            'skin_type_score': round(skin_score, 3),
            'age_score': round(age_score, 3),
            'gender_score': round(gender_score, 3),
            'reasoning': reasoning,
        }
    
    @classmethod
    def _generate_reasoning(cls, product, skin_type, age, gender,
                           skin_score, age_score, gender_score):
        """
        Generate human-readable match reasoning
        
        Example:
        "Perfect for oily skin. Suitable for your age group (20-30). 
         Great for women."
        """
        
        reasons = []
        
        # Skin type reasoning
        if skin_score >= 0.9:
            reasons.append(f"Perfect for {skin_type} skin")
        elif skin_score >= 0.7:
            reasons.append(f"Good for {skin_type} skin")
        else:
            reasons.append(f"Suitable for various skin types including {skin_type}")
        
        # Age reasoning
        if age_score >= 0.8:
            reasons.append(
                f"Ideal for your age group ({product.min_age}-{product.max_age})"
            )
        elif age_score >= 0.5:
            reasons.append(f"Suitable for ages {product.min_age}-{product.max_age}")
        
        # Gender reasoning
        if gender_score >= 0.9:
            if product.gender == 'unisex':
                reasons.append("Suitable for everyone")
            else:
                reasons.append(f"Designed for {gender}")
        
        # Product highlights
        if product.discount_percent > 0:
            reasons.append(f"{product.discount_percent}% off!")
        
        if product.is_featured:
            reasons.append("Featured product")
        
        return ". ".join(reasons) + "."
    
    @classmethod
    def save_recommendations(cls, analysis_id, recommendation_data):
        """
        Save recommendations to database
        
        Args:
            analysis_id: SkinAnalysis ID
            recommendation_data: Result from get_recommendations()
        
        Returns:
            list: Saved Recommendation objects
        """
        
        try:
            analysis = SkinAnalysis.objects.get(id=analysis_id)
        except SkinAnalysis.DoesNotExist:
            raise ValueError(f"Analysis {analysis_id} not found!")
        
        # Clear old recommendations (if re-analyzing)
        Recommendation.objects.filter(analysis=analysis).delete()
        
        # Save session metadata
        session, _ = RecommendationSession.objects.update_or_create(
            analysis=analysis,
            defaults={
                'total_products_matched': recommendation_data['total_matched'],
                'algorithm_version': 'v1.0',
                'filters_applied': {
                    'skin_type': analysis.skin_type,
                    'age': analysis.age,
                    'gender': analysis.gender,
                },
                'processing_time_ms': recommendation_data['processing_time_ms'],
            }
        )
        
        # Save recommendations
        saved_recommendations = []
        
        for rank, item in enumerate(recommendation_data['recommendations'], start=1):
            recommendation = Recommendation.objects.create(
                analysis=analysis,
                product=item['product'],
                match_score=item['match_score'],
                rank=rank,
                skin_type_match=item['skin_type_match'],
                age_match=item['age_match'],
                gender_match=item['gender_match'],
                reasoning=item['reasoning'],
            )
            saved_recommendations.append(recommendation)
        
        return saved_recommendations
    
    @classmethod
    def get_similar_products(cls, product_id, limit=6):
        """
        Get similar products
        
        Based on:
        - Same category
        - Same skin type
        - Similar price range
        
        Args:
            product_id: Product ID
            limit: Number of similar products
        
        Returns:
            QuerySet: Similar products
        """
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Product.objects.none()
        
        # Price range ±30%
        price_min = product.price * 0.7
        price_max = product.price * 1.3
        
        similar = Product.objects.filter(
            category=product.category,
            suitable_skin_type=product.suitable_skin_type,
            price__gte=price_min,
            price__lte=price_max,
            is_available=True
        ).exclude(id=product_id)[:limit]
        
        return similar