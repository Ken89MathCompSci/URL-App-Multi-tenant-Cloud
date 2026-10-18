output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = aws_lb.app.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL (without tag)"
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.app.name
}

output "efs_filesystem_id" {
  description = "EFS filesystem ID"
  value       = aws_efs_file_system.app.id
}
