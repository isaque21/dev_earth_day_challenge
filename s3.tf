# Gerador de sufixo único para o nome do bucket
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Bucket S3 para hospedagem do frontend
resource "aws_s3_bucket" "frontend_bucket" {
  # O lower() garante que todas as letras fiquem minúsculas
  bucket        = "${lower(var.project_name)}-frontend-${random_id.bucket_suffix.hex}"
  force_destroy = true 
}

# Bloqueio de acesso público total (Melhor prática SecOps)
resource "aws_s3_bucket_public_access_block" "frontend_block" {
  bucket = aws_s3_bucket.frontend_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Política do Bucket: Permite que APENAS o CloudFront leia os arquivos via OAC
resource "aws_s3_bucket_policy" "allow_access_from_cloudfront" {
  bucket = aws_s3_bucket.frontend_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipalReadOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend_bucket.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.s3_distribution.arn
          }
        }
      }
    ]
  })
}