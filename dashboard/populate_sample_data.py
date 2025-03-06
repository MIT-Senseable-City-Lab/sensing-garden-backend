#!/usr/bin/env python3
import boto3
import uuid
import base64
import io
from PIL import Image, ImageDraw
from datetime import datetime, timedelta
import random
import os
from decimal import Decimal

# Configure AWS
aws_region = os.environ.get('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=aws_region)
s3 = boto3.client('s3', region_name=aws_region)

# Table and bucket names
DETECTIONS_TABLE = 'sensor_detections'
CLASSIFICATIONS_TABLE = 'sensor_classifications'
MODELS_TABLE = 'models'
IMAGES_BUCKET = 'sensing-garden-images'

# Sample data
DEVICE_IDS = ['device-001', 'device-002', 'device-003']
MODEL_IDS = ['model-001', 'model-002']
SPECIES = [
    {'genus': 'Solanum', 'family': 'Solanaceae', 'species': 'Solanum lycopersicum', 'common': 'Tomato'},
    {'genus': 'Capsicum', 'family': 'Solanaceae', 'species': 'Capsicum annuum', 'common': 'Bell Pepper'},
    {'genus': 'Lactuca', 'family': 'Asteraceae', 'species': 'Lactuca sativa', 'common': 'Lettuce'},
    {'genus': 'Spinacia', 'family': 'Amaranthaceae', 'species': 'Spinacia oleracea', 'common': 'Spinach'},
    {'genus': 'Cucumis', 'family': 'Cucurbitaceae', 'species': 'Cucumis sativus', 'common': 'Cucumber'}
]

def create_test_image(text):
    """Create a simple test image with text"""
    # Create a simple image with text
    img = Image.new('RGB', (300, 200), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10, 10), text, fill=(255, 255, 0))
    
    # Save to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr = img_byte_arr.getvalue()
    
    return img_byte_arr

def upload_image_to_s3(image_data, key):
    """Upload image to S3"""
    try:
        s3.put_object(
            Bucket=IMAGES_BUCKET,
            Key=key,
            Body=image_data,
            ContentType='image/jpeg'
        )
        return f"https://{IMAGES_BUCKET}.s3.amazonaws.com/{key}"
    except Exception as e:
        print(f"Error uploading to S3: {str(e)}")
        return ""

def create_model_data():
    """Create sample model data"""
    models_table = dynamodb.Table(MODELS_TABLE)
    
    # Add detection model
    detection_model = {
        'id': 'model-001',
        'timestamp': datetime.utcnow().isoformat(),
        'type': 'detection',
        'name': 'Plant Detection v1',
        'version': '1.0.0',
        'description': 'Model for detecting plants in images'
    }
    
    # Add classification model
    classification_model = {
        'id': 'model-002',
        'timestamp': (datetime.utcnow() - timedelta(days=1)).isoformat(),
        'type': 'classification',
        'name': 'Plant Classification v1',
        'version': '1.0.0',
        'description': 'Model for classifying plant species'
    }
    
    try:
        models_table.put_item(Item=detection_model)
        print(f"Added detection model: {detection_model['id']}")
        
        models_table.put_item(Item=classification_model)
        print(f"Added classification model: {classification_model['id']}")
        
        return True
    except Exception as e:
        print(f"Error creating model data: {str(e)}")
        return False

def create_detection_data(num_items=5):
    """Create sample detection data"""
    detections_table = dynamodb.Table(DETECTIONS_TABLE)
    
    for i in range(num_items):
        device_id = random.choice(DEVICE_IDS)
        model_id = 'model-001'  # Detection model
        timestamp = (datetime.utcnow() - timedelta(hours=i)).isoformat()
        
        # Create and upload image
        image_data = create_test_image(f"Detection {i+1} - {device_id}")
        s3_key = f"detections/{device_id}/{datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')}-{i}.jpg"
        s3_image_link = upload_image_to_s3(image_data, s3_key)
        
        # Create detection item
        detection_item = {
            'device_id': device_id,
            'model_id': model_id,
            'timestamp': timestamp,
            'image_link': s3_image_link
        }
        
        try:
            detections_table.put_item(Item=detection_item)
            print(f"Added detection item {i+1}: {device_id}")
        except Exception as e:
            print(f"Error adding detection item: {str(e)}")

def create_classification_data(num_items=5):
    """Create sample classification data"""
    classifications_table = dynamodb.Table(CLASSIFICATIONS_TABLE)
    
    for i in range(num_items):
        device_id = random.choice(DEVICE_IDS)
        model_id = 'model-002'  # Classification model
        timestamp = (datetime.utcnow() - timedelta(hours=i)).isoformat()
        plant = random.choice(SPECIES)
        
        # Create and upload image
        image_data = create_test_image(f"Classification {i+1} - {plant['common']}")
        s3_key = f"classifications/{device_id}/{datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')}-{i}.jpg"
        s3_image_link = upload_image_to_s3(image_data, s3_key)
        
        # Create classification item
        classification_item = {
            'device_id': device_id,
            'model_id': model_id,
            'timestamp': timestamp,
            'image_link': s3_image_link,
            'family': plant['family'],
            'genus': plant['genus'],
            'species': plant['species'],
            'family_confidence': Decimal(str(round(random.uniform(0.75, 0.99), 2))),
            'genus_confidence': Decimal(str(round(random.uniform(0.75, 0.99), 2))),
            'species_confidence': Decimal(str(round(random.uniform(0.75, 0.99), 2)))
        }
        
        try:
            classifications_table.put_item(Item=classification_item)
            print(f"Added classification item {i+1}: {device_id} - {plant['species']}")
        except Exception as e:
            print(f"Error adding classification item: {str(e)}")

if __name__ == "__main__":
    print("Populating DynamoDB with sample data...")
    
    # Create model data
    print("\nCreating model data...")
    create_model_data()
    
    # Create detection data
    print("\nCreating detection data...")
    create_detection_data(5)
    
    # Create classification data
    print("\nCreating classification data...")
    create_classification_data(5)
    
    print("\nSample data population complete!")
