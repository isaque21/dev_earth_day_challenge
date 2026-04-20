# Role que permite a Lambda ser executada
resource "aws_iam_role" "lambda_exec_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Permissões específicas: Logs, DynamoDB e SNS
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-policy"
  role = aws_iam_role.lambda_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.geoalert_history.arn,
          "${aws_dynamodb_table.geoalert_history.arn}/index/LocationCacheIndex"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.gemini_key.arn,
          aws_secretsmanager_secret.owm_key.arn,
          aws_secretsmanager_secret.nasa_key.arn
        ]
      }
    ]
  })
}