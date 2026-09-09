output "service_url" {
  value = "https://${aws_apprunner_service.app.service_url}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
