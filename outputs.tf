output "lambda_arn" {
  value = aws_lambda_function.geoalert_processor.arn
}

output "dynamodb_table" {
  value = aws_dynamodb_table.geoalert_history.name
}

output "website_url" {
  description = "URL do site no CloudFront"
  value       = "https://${aws_cloudfront_distribution.s3_distribution.domain_name}"
}

output "api_endpoint" {
  description = "URL do endpoint da API para o frontend"
  value       = "${aws_api_gateway_stage.api_stage.invoke_url}/analisar"
}