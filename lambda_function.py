import os
import json
import boto3
import urllib.request
import urllib.error
import uuid
import logging
import re
from datetime import datetime
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')

def mask_api_key(url):
    url = re.sub(r'appid=[^&]+', 'appid=***MASKED***', url)
    url = re.sub(r'key=[^&]+', 'key=***MASKED***', url)
    url = re.sub(r'/csv/[^/]+/', '/csv/***MASKED***/', url)
    return url

def get_secret(env_var_name):
    secret_arn = os.environ.get(env_var_name)
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return response['SecretString'].strip()
    except Exception as e:
        logger.error(f"[SECRETS ERROR] Failed to fetch {env_var_name}: {e}")
        raise

def check_cache(lat, lon):
    table_name = os.environ.get('DYNAMO_TABLE')
    table = dynamodb.Table(table_name)
    
    # Atualizado para v2 para não puxar o cache sem o overview
    cache_key = f"{round(lat, 2)},{round(lon, 2)}_en_v2" 
    logger.info(f"[CACHE] Checking cache for key: {cache_key}")
    
    try:
        response = table.query(
            IndexName='LocationCacheIndex',
            KeyConditionExpression=Key('coordenadas_cache').eq(cache_key),
            ScanIndexForward=False,
            Limit=1
        )
        if response['Items']:
            latest_item = response['Items'][0]
            ts_dt = datetime.fromisoformat(latest_item['timestamp'])
            diff = datetime.utcnow() - ts_dt
            if diff.total_seconds() < 1800:
                logger.info(f"[CACHE HIT] Success! Returning data from {int(diff.total_seconds()/60)} mins ago.")
                return json.loads(latest_item['dados'])
        logger.info("[CACHE MISS] No valid recent analysis found.")
        return None
    except Exception as e:
        logger.warning(f"[CACHE BYPASS] DynamoDB query failed: {e}")
        return None

def get_enhanced_weather_data(lat, lon, owm_key, nasa_key):
    logger.info(f"========== STARTING DATA COLLECTION (Lat: {lat}, Lon: {lon}) ==========")
    owm_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={owm_key}&units=metric&lang=en"
    weather_data = {}
    try:
        req = urllib.request.Request(owm_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            weather_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"[HTTP ERROR] OWM failed: {e}")

    min_lon, min_lat = lon - 0.5, lat - 0.5
    max_lon, max_lat = lon + 0.5, lat + 0.5
    nasa_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{nasa_key}/VIIRS_SNPP_NRT/{min_lon},{min_lat},{max_lon},{max_lat}/1"
    focos_calor = 0
    try:
        req = urllib.request.Request(nasa_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            csv_lines = response.read().decode('utf-8').strip().split('\n')
            if len(csv_lines) > 1:
                focos_calor = len(csv_lines) - 1
    except Exception as e:
        logger.warning(f"[HTTP ERROR] NASA failed: {e}")

    data = {
        "coordinates": f"{lat}, {lon}",
        "city": weather_data.get("name", "Unknown Location"),
        "country": weather_data.get("sys", {}).get("country", ""),
        "climate": {
            "current_celsius": weather_data.get("main", {}).get("temp", 0),
            "humidity_percent": weather_data.get("main", {}).get("humidity", 0),
            "general_description": weather_data.get("weather", [{}])[0].get("description", ""),
            "rain_1h_mm": weather_data.get("rain", {}).get("1h", 0)
        },
        "nasa_satellite": {"nearby_fire_hotspots": focos_calor}
    }
    return data

def analyze_catastrophe_risk(api_key, data):
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    # Prompt atualizado pedindo o Ecological Overview
    prompt = f"""
    Act as a Global Civil Defense Catastrophe Alert system and Ecological Analyst.
    Analyze the following real-time climate and satellite data for {data['city']}, {data['country']}:
    {json.dumps(data)}

    Task 1: Classify the threat level (LOW, MEDIUM, HIGH) for 5 natural disasters based on current weather. Briefly justify each in 1 short English sentence.
    Task 2: Provide a brief ecological overview of the region based on your knowledge of the location. Keep each point to 1-2 short sentences.

    STRICTLY RETURN THE JSON BELOW. NO MARKDOWN (without ```json tags):
    {{
        "location": "{data['city']}, {data['country']}",
        "temperature": "{data['climate']['current_celsius']}°C | {round((data['climate']['current_celsius'] * 9/5) + 32, 1)}°F",
        "humidity": "{data['climate']['humidity_percent']}%",
        "climate_desc": "1-sentence summary of the general weather conditions.",
        "riscos": {{
            "extreme_heat": {{"level": "LOW", "reason": "..."}},
            "extreme_cold": {{"level": "LOW", "reason": "..."}},
            "wildfires": {{"level": "LOW", "reason": "..."}},
            "floods": {{"level": "LOW", "reason": "..."}},
            "landslides": {{"level": "LOW", "reason": "..."}}
        }},
        "ecological_overview": {{
            "vegetation_type": "...",
            "natural_attractions": "...",
            "conservation_status": "...",
            "ecosystem_quality": "..."
        }}
    }}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_gemini = response.read().decode('utf-8')
            result = json.loads(raw_gemini)
            gemini_text = result['candidates'][0]['content']['parts'][0]['text']
            gemini_text = gemini_text.replace("```json\n", "").replace("```", "").strip()
            return json.loads(gemini_text)
    except Exception as e:
        logger.error(f"[HTTP ERROR] Gemini failed: {e}")
        return None

def lambda_handler(event, context):
    try:
        body = event.get('body', '{}')
        if isinstance(body, str):
            try: body = json.loads(body)
            except: body = {}
                
        lat = float(body.get('lat', -21.7545))
        lon = float(body.get('lon', -43.3504))

        cached_data = check_cache(lat, lon)
        if cached_data:
            return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*", "X-Cache": "HIT"}, "body": json.dumps(cached_data)}
        
        owm_key = get_secret('OWM_SECRET_ARN')
        nasa_key = get_secret('NASA_SECRET_ARN')
        gemini_key = get_secret('GEMINI_SECRET_ARN')
        
        env_data = get_enhanced_weather_data(lat, lon, owm_key, nasa_key)
        risk_analysis = analyze_catastrophe_risk(gemini_key, env_data)
        
        if not risk_analysis:
            raise ValueError("Gemini model returned invalid data or timed out.")

        table_name = os.environ.get('DYNAMO_TABLE')
        cache_key = f"{round(lat, 2)},{round(lon, 2)}_en_v2"
        
        dynamodb.Table(table_name).put_item(
            Item={
                'alert_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow().isoformat(),
                'coordenadas_cache': cache_key,
                'dados': json.dumps(risk_analysis)
            }
        )
        return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*", "X-Cache": "MISS"}, "body": json.dumps(risk_analysis)}

    except Exception as e:
        logger.error(f"[CRITICAL ERROR] {e}", exc_info=True)
        return {"statusCode": 500, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": str(e)})}