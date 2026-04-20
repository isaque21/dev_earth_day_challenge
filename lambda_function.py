import os
import json
import boto3
import urllib.request
import urllib.error
import uuid
import logging
import re
import time
from datetime import datetime
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')


class GeminiAPIError(Exception):
    def __init__(self, status_code, message, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.retry_after = retry_after


def elapsed_ms(start_time):
    return int((time.time() - start_time) * 1000)

def mask_api_key(url):
    url = re.sub(r'appid=[^&]+', 'appid=***MASKED***', url)
    url = re.sub(r'key=[^&]+', 'key=***MASKED***', url)
    url = re.sub(r'/csv/[^/]+/', '/csv/***MASKED***/', url)
    return url


def parse_retry_delay_seconds(error_payload):
    try:
        details = error_payload.get("error", {}).get("details", [])
        for detail in details:
            retry_delay = detail.get("retryDelay")
            if retry_delay and retry_delay.endswith("s"):
                return int(float(retry_delay[:-1]))
    except Exception:
        return None
    return None

def get_secret(env_var_name):
    secret_arn = os.environ.get(env_var_name)
    logger.info(f"[SECRETS] Fetching secret for {env_var_name}.")
    start_time = time.time()
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        logger.info(f"[SECRETS] Retrieved secret for {env_var_name} in {elapsed_ms(start_time)} ms.")
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
    start_time = time.time()
    
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
                logger.info(
                    f"[CACHE HIT] Success! Returning data from {int(diff.total_seconds()/60)} mins ago. "
                    f"Lookup completed in {elapsed_ms(start_time)} ms."
                )
                return json.loads(latest_item['dados'])
        logger.info(f"[CACHE MISS] No valid recent analysis found. Lookup completed in {elapsed_ms(start_time)} ms.")
        return None
    except Exception as e:
        logger.warning(f"[CACHE BYPASS] DynamoDB query failed: {e}")
        return None

def get_enhanced_weather_data(lat, lon, owm_key, nasa_key):
    logger.info(f"========== STARTING DATA COLLECTION (Lat: {lat}, Lon: {lon}) ==========")
    owm_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={owm_key}&units=metric&lang=en"
    weather_data = {}
    weather_start = time.time()
    logger.info(f"[OWM] Requesting current weather data from {mask_api_key(owm_url)}")
    try:
        req = urllib.request.Request(owm_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            weather_data = json.loads(response.read().decode('utf-8'))
        logger.info(
            "[OWM] Weather data retrieved in %s ms. City=%s Country=%s Temp=%sC Humidity=%s%%",
            elapsed_ms(weather_start),
            weather_data.get("name", "Unknown"),
            weather_data.get("sys", {}).get("country", ""),
            weather_data.get("main", {}).get("temp", "n/a"),
            weather_data.get("main", {}).get("humidity", "n/a")
        )
    except Exception as e:
        logger.error(f"[HTTP ERROR] OWM failed: {e}")

    min_lon, min_lat = lon - 0.5, lat - 0.5
    max_lon, max_lat = lon + 0.5, lat + 0.5
    nasa_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{nasa_key}/VIIRS_SNPP_NRT/{min_lon},{min_lat},{max_lon},{max_lat}/1"
    focos_calor = 0
    nasa_start = time.time()
    logger.info(f"[NASA] Requesting hotspot data from {mask_api_key(nasa_url)}")
    try:
        req = urllib.request.Request(nasa_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            csv_lines = response.read().decode('utf-8').strip().split('\n')
            if len(csv_lines) > 1:
                focos_calor = len(csv_lines) - 1
        logger.info(
            f"[NASA] Hotspot data retrieved in {elapsed_ms(nasa_start)} ms. Nearby hotspots={focos_calor}."
        )
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
    logger.info(
        "[DATA] Consolidated environmental payload: city=%s country=%s temp=%sC humidity=%s%% rain_1h=%s hotspots=%s",
        data["city"],
        data["country"],
        data["climate"]["current_celsius"],
        data["climate"]["humidity_percent"],
        data["climate"]["rain_1h_mm"],
        data["nasa_satellite"]["nearby_fire_hotspots"]
    )
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
    retryable_statuses = {429, 500, 502, 503, 504}
    max_attempts = 3
    last_status_code = None
    last_reason = None
    last_error_payload = {}

    logger.info(
        "[GEMINI] Starting risk analysis with model=%s for location=%s, %s.",
        model_name,
        data.get("city", "Unknown Location"),
        data.get("country", "")
    )

    for attempt in range(1, max_attempts + 1):
        attempt_start = time.time()
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        logger.info(
            "[GEMINI] Attempt %s/%s sending request to %s",
            attempt,
            max_attempts,
            mask_api_key(url)
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw_gemini = response.read().decode('utf-8')
                result = json.loads(raw_gemini)
                gemini_text = result['candidates'][0]['content']['parts'][0]['text']
                gemini_text = gemini_text.replace("```json\n", "").replace("```", "").strip()
                parsed_result = json.loads(gemini_text)
                logger.info(
                    "[GEMINI] Attempt %s/%s succeeded in %s ms. Threat keys=%s Ecological overview=%s",
                    attempt,
                    max_attempts,
                    elapsed_ms(attempt_start),
                    list(parsed_result.get("riscos", {}).keys()),
                    "present" if parsed_result.get("ecological_overview") else "missing"
                )
                return parsed_result
        except urllib.error.HTTPError as e:
            error_body = ""
            error_payload = {}
            try:
                error_body = e.read().decode('utf-8', errors='replace')
                error_payload = json.loads(error_body) if error_body else {}
            except Exception:
                error_body = "<unable to decode error body>"
                error_payload = {}

            last_status_code = e.code
            last_reason = e.reason
            last_error_payload = error_payload

            logger.error(
                "[HTTP ERROR] Gemini attempt %s/%s failed in %s ms with status %s (%s). URL: %s. Response body: %s",
                attempt,
                max_attempts,
                elapsed_ms(attempt_start),
                e.code,
                e.reason,
                mask_api_key(url),
                error_body
            )

            if e.code in retryable_statuses and attempt < max_attempts:
                sleep_seconds = 2 ** (attempt - 1)
                retry_after = parse_retry_delay_seconds(error_payload)
                if retry_after is not None:
                    sleep_seconds = max(sleep_seconds, retry_after)
                logger.warning(
                    "[RETRY] Gemini retrying in %s second(s) after transient status %s.",
                    sleep_seconds,
                    e.code
                )
                time.sleep(sleep_seconds)
                continue
            break
        except Exception as e:
            logger.error(
                f"[HTTP ERROR] Gemini failed on attempt {attempt}/{max_attempts} after {elapsed_ms(attempt_start)} ms: {e}"
            )
            return None

    if last_status_code == 429:
        raise GeminiAPIError(
            429,
            f"Gemini quota exceeded for {model_name}. Check plan, billing, or daily free-tier usage.",
            retry_after=parse_retry_delay_seconds(last_error_payload)
        )

    if last_status_code == 503:
        raise GeminiAPIError(
            503,
            "Gemini model is temporarily unavailable due to high demand. Please retry shortly."
        )

    if last_status_code:
        raise GeminiAPIError(
            502,
            f"Gemini request failed after retries with status {last_status_code} ({last_reason})."
        )

    return None

def lambda_handler(event, context):
    request_start = time.time()
    try:
        logger.info(
            "[REQUEST] Lambda invocation started. RequestId=%s RemainingTimeMs=%s",
            getattr(context, "aws_request_id", "unknown"),
            context.get_remaining_time_in_millis() if context else "unknown"
        )
        body = event.get('body', '{}')
        logger.info(f"[REQUEST] Raw body type={type(body).__name__}")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                logger.warning("[REQUEST] Failed to parse JSON body. Falling back to empty payload.")
                body = {}
                
        lat = float(body.get('lat', -21.7545))
        lon = float(body.get('lon', -43.3504))
        logger.info(f"[REQUEST] Parsed coordinates lat={lat}, lon={lon}")

        cached_data = check_cache(lat, lon)
        if cached_data:
            logger.info(f"[RESPONSE] Returning cached response in {elapsed_ms(request_start)} ms.")
            return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*", "X-Cache": "HIT"}, "body": json.dumps(cached_data)}
        
        logger.info("[FLOW] Cache miss confirmed. Fetching upstream secrets.")
        owm_key = get_secret('OWM_SECRET_ARN')
        nasa_key = get_secret('NASA_SECRET_ARN')
        gemini_key = get_secret('GEMINI_SECRET_ARN')
        logger.info("[FLOW] Secrets loaded successfully. Starting environmental data collection.")
        
        env_data = get_enhanced_weather_data(lat, lon, owm_key, nasa_key)
        logger.info("[FLOW] Environmental data collection completed. Starting Gemini analysis.")
        risk_analysis = analyze_catastrophe_risk(gemini_key, env_data)
        
        if not risk_analysis:
            raise ValueError("Gemini model returned invalid data or timed out.")

        table_name = os.environ.get('DYNAMO_TABLE')
        cache_key = f"{round(lat, 2)},{round(lon, 2)}_en_v2"
        logger.info(f"[CACHE WRITE] Persisting fresh analysis to DynamoDB table={table_name} cache_key={cache_key}")
        
        dynamodb.Table(table_name).put_item(
            Item={
                'alert_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow().isoformat(),
                'coordenadas_cache': cache_key,
                'dados': json.dumps(risk_analysis)
            }
        )
        logger.info(f"[CACHE WRITE] DynamoDB persistence completed. Total request time={elapsed_ms(request_start)} ms.")
        logger.info("[RESPONSE] Returning fresh analysis response with X-Cache=MISS.")
        return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*", "X-Cache": "MISS"}, "body": json.dumps(risk_analysis)}

    except GeminiAPIError as e:
        headers = {"Access-Control-Allow-Origin": "*"}
        body = {"error": e.message}
        if e.retry_after is not None:
            headers["Retry-After"] = str(e.retry_after)
            body["retry_after_seconds"] = e.retry_after
        logger.error(f"[GEMINI ERROR] {e.message}. Total request time={elapsed_ms(request_start)} ms.")
        return {"statusCode": e.status_code, "headers": headers, "body": json.dumps(body)}
    except Exception as e:
        logger.error(f"[CRITICAL ERROR] {e}. Total request time={elapsed_ms(request_start)} ms.", exc_info=True)
        return {"statusCode": 500, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": str(e)})}
