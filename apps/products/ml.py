import os
import joblib
import numpy as np
import pandas as pd
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings

from apps.products.models.products_models import StockBatch, Product
from apps.products.models.supply_chain import InventoryTransaction

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'expiry_model.joblib')

def get_sales_velocity(product, days=30):
    """
    Calculate the total units sold/consumed in the last X days.
    """
    cutoff = timezone.now() - timedelta(days=days)
    # Filter outbound transactions (negative quantity change)
    transactions = InventoryTransaction.objects.filter(
        product=product,
        created_at__gte=cutoff,
        quantity_change__lt=0
    )
    total_outbound = transactions.aggregate(total=Sum('quantity_change'))['total'] or 0
    return abs(total_outbound)

def generate_training_data():
    """
    Generate training data from actual database records.
    If database records are insufficient, synthetic records are generated to seed the ML model.
    """
    data = []
    
    # 1. Fetch historical/active batches to build real training rows
    batches = StockBatch.objects.select_related('product', 'storage_location').all()
    
    for batch in batches:
        days_to_expiry = (batch.expiry_date - timezone.now().date()).days if batch.expiry_date else 90
        qty = batch.quantity
        temp = float(batch.storage_location.temperature) if batch.storage_location and batch.storage_location.temperature is not None else 20.0
        humidity = float(batch.storage_location.humidity) if batch.storage_location and batch.storage_location.humidity is not None else 50.0
        velocity = get_sales_velocity(batch.product)
        
        # Target: 1 if expired, or if days to expiry is very low and sales velocity is insufficient
        # 0 if sales velocity easily clears the quantity before expiry
        if days_to_expiry < 0:
            will_expire = 1
        elif velocity > 0 and (qty / (velocity / 30.0)) > days_to_expiry:
            will_expire = 1
        elif days_to_expiry <= 7:
            will_expire = 1
        else:
            will_expire = 0
            
        data.append({
            'days_to_expiry': days_to_expiry,
            'quantity': qty,
            'temperature': temp,
            'humidity': humidity,
            'sales_velocity': velocity,
            'will_expire': will_expire
        })
        
    # 2. Add synthetic data if size is small, to ensure robust training
    if len(data) < 100:
        np.random.seed(42)
        for _ in range(150 - len(data)):
            # Random features
            days = int(np.random.randint(-10, 120))
            qty = int(np.random.randint(1, 500))
            temp = float(np.random.normal(20, 5))
            hum = float(np.random.normal(50, 10))
            velocity = int(np.random.randint(0, 100))
            
            # Simple simulation logic for training labels
            daily_sales = velocity / 30.0
            if days < 0:
                will_expire = 1
            elif daily_sales == 0:
                will_expire = 1 if days < 30 else 0
            elif (qty / daily_sales) > days:
                will_expire = 1
            elif days <= 7:
                will_expire = 1
            elif days > 60:
                will_expire = 0
            else:
                # Moderate chance
                will_expire = 1 if np.random.rand() < 0.3 else 0
                
            data.append({
                'days_to_expiry': days,
                'quantity': qty,
                'temperature': temp,
                'humidity': hum,
                'sales_velocity': velocity,
                'will_expire': will_expire
            })
            
    return pd.DataFrame(data)

def train_expiry_model():
    """
    Train and save the Random Forest model for predicting expiry risk.
    """
    from sklearn.ensemble import RandomForestClassifier
    
    df = generate_training_data()
    
    X = df[['days_to_expiry', 'quantity', 'temperature', 'humidity', 'sales_velocity']]
    y = df['will_expire']
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # Save the model to disk
    joblib.dump(model, MODEL_PATH)
    return True

def predict_batch_risk(batch):
    """
    Predict expiry risk probability and risk tier for a single StockBatch.
    If the model doesn't exist on disk, train it first.
    """
    # Auto-train if model doesn't exist
    if not os.path.exists(MODEL_PATH):
        train_expiry_model()
        
    try:
        model = joblib.load(MODEL_PATH)
    except Exception:
        # Fallback to rule-based prediction if loading fails
        return fallback_prediction(batch)
        
    days_to_expiry = (batch.expiry_date - timezone.now().date()).days if batch.expiry_date else 90
    qty = batch.quantity
    temp = float(batch.storage_location.temperature) if batch.storage_location and batch.storage_location.temperature is not None else 20.0
    humidity = float(batch.storage_location.humidity) if batch.storage_location and batch.storage_location.humidity is not None else 50.0
    velocity = get_sales_velocity(batch.product)
    
    feature_vector = np.array([[days_to_expiry, qty, temp, humidity, velocity]])
    
    try:
        # Predict probability of class 1 (will expire)
        prob = model.predict_proba(feature_vector)[0][1]
    except Exception:
        prob = float(fallback_prediction(batch)[0])
        
    # Tier classification based strictly on Requirement 4:
    # Critical (expiry within 7 days)
    # High (8-30 days)
    # Medium (31-60 days)
    # Low (>60 days)
    if days_to_expiry <= 7:
        tier = 'critical'
    elif 8 <= days_to_expiry <= 30:
        tier = 'high'
    elif 31 <= days_to_expiry <= 60:
        tier = 'medium'
    else:
        tier = 'low'
        
    return prob, tier

def fallback_prediction(batch):
    """
    Simple fallback prediction in case ML model loading fails.
    """
    days_to_expiry = (batch.expiry_date - timezone.now().date()).days if batch.expiry_date else 90
    if days_to_expiry <= 0:
        prob = 1.0
        tier = 'critical'
    elif days_to_expiry <= 7:
        prob = 0.90
        tier = 'critical'
    elif days_to_expiry <= 30:
        prob = 0.60
        tier = 'high'
    elif days_to_expiry <= 60:
        prob = 0.30
        tier = 'medium'
    else:
        prob = 0.05
        tier = 'low'
    return prob, tier

def run_expiry_predictions_for_all_batches():
    """
    Evaluate all active stock batches, compute their risk probability and risk tier,
    and save the results to the database.
    Returns the count of evaluated batches.
    """
    batches = StockBatch.objects.all()
    count = 0
    for batch in batches:
        prob, tier = predict_batch_risk(batch)
        batch.risk_probability = prob
        batch.risk_tier = tier
        batch.save()
        count += 1
    return count
