# --- REST API ---
resource "aws_api_gateway_rest_api" "geoalert_api" {
  name        = "GeoAlertAPI"
  description = "Interface para analise de risco ambiental"
}

# Endpoint /analisar
resource "aws_api_gateway_resource" "analisar" {
  rest_api_id = aws_api_gateway_rest_api.geoalert_api.id
  parent_id   = aws_api_gateway_rest_api.geoalert_api.root_resource_id
  path_part   = "analisar"
}

# Método POST
resource "aws_api_gateway_method" "post_method" {
  rest_api_id   = aws_api_gateway_rest_api.geoalert_api.id
  resource_id   = aws_api_gateway_resource.analisar.id
  http_method   = "POST"
  authorization = "NONE"
}

# Integração com Lambda (Proxy)
resource "aws_api_gateway_integration" "lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.geoalert_api.id
  resource_id             = aws_api_gateway_resource.analisar.id
  http_method             = aws_api_gateway_method.post_method.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.geoalert_processor.invoke_arn
}

# --- Configuração de CORS (Essencial para o Frontend) ---
module "cors" {
  source  = "squidfunk/api-gateway-enable-cors/aws"
  version = "0.3.3"

  api_id          = aws_api_gateway_rest_api.geoalert_api.id
  api_resource_id = aws_api_gateway_resource.analisar.id
}

# Deployment e Stage
resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on  = [aws_api_gateway_integration.lambda_integration]
  rest_api_id = aws_api_gateway_rest_api.geoalert_api.id
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.geoalert_api.id
  stage_name    = "prod"
}

# Permissão para o API Gateway invocar a Lambda
resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.geoalert_processor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.geoalert_api.execution_arn}/*/*"
}