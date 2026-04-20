variable "aws_region" {
  description = "Região da AWS"
  default     = "us-east-1"
}

variable "gemini_api_key" {
  description = "Chave da API do Google Gemini (Google AI Studio)"
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Nome do projeto para tags"
  default     = "GeoAlert"
}

variable "gemini_model" {
  description = "Versão do modelo do Google Gemini a ser utilizada"
  default     = "gemini-3.1-flash-lite-preview"
}

variable "openweathermap_api_key" {
  description = "Chave da API do OpenWeatherMap"
  type        = string
  sensitive   = true
}

variable "nasa_firms_api_key" {
  description = "Chave da API do NASA FIRMS"
  type        = string
  sensitive   = true
}
