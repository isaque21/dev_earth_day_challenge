# --- Banco de Dados ---
resource "aws_dynamodb_table" "geoalert_history" {
  name         = "GeoAlertHistory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "alert_id"

  attribute {
    name = "alert_id"
    type = "S"
  }

  # Atributos para o Cache
  attribute {
    name = "coordenadas_cache"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # Índice para busca rápida por localização
  global_secondary_index {
    name               = "LocationCacheIndex"
    hash_key           = "coordenadas_cache"
    range_key          = "timestamp"
    projection_type    = "ALL"
  }
}

# --- Secrets Manager ---
resource "aws_secretsmanager_secret" "gemini_key" {
  name                    = "geoalert/gemini_api_key"
  recovery_window_in_days = 0
}
resource "aws_secretsmanager_secret_version" "gemini_key_version" {
  secret_id     = aws_secretsmanager_secret.gemini_key.id
  secret_string = var.gemini_api_key
}

resource "aws_secretsmanager_secret" "owm_key" {
  name                    = "geoalert/owm_api_key"
  recovery_window_in_days = 0
}
resource "aws_secretsmanager_secret_version" "owm_key_version" {
  secret_id     = aws_secretsmanager_secret.owm_key.id
  secret_string = var.openweathermap_api_key
}

resource "aws_secretsmanager_secret" "nasa_key" {
  name                    = "geoalert/nasa_api_key"
  recovery_window_in_days = 0
}
resource "aws_secretsmanager_secret_version" "nasa_key_version" {
  secret_id     = aws_secretsmanager_secret.nasa_key.id
  secret_string = var.nasa_firms_api_key
}

# --- Função Lambda ---
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "geoalert_processor" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "GeoAlertProcessor"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  timeout          = 45 # Aumentado para suportar 3 chamadas de API
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      GEMINI_SECRET_ARN = aws_secretsmanager_secret.gemini_key.arn
      OWM_SECRET_ARN    = aws_secretsmanager_secret.owm_key.arn
      NASA_SECRET_ARN   = aws_secretsmanager_secret.nasa_key.arn
      DYNAMO_TABLE      = aws_dynamodb_table.geoalert_history.name
      AWS_REGION_NAME   = var.aws_region
      GEMINI_MODEL      = var.gemini_model
    }
  }
}

# --- Agendamento (EventBridge) ---
resource "aws_cloudwatch_event_rule" "hourly_trigger" {
  name                = "geoalert_hourly_trigger"
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.hourly_trigger.name
  arn       = aws_lambda_function.geoalert_processor.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.geoalert_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_trigger.arn
}