# ── Security Group: ECS Tasks ─────────────────────────────────────────────────

resource "aws_security_group" "sg_ecs" {
  name        = "${var.app_name}-sg-ecs"
  description = "Allow inbound from ALB on app port; all outbound"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "App port from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_alb.id]
  }

  egress {
    description = "All outbound (ECR pull, EFS NFS, CloudWatch)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-sg-ecs" }
}

# ── CloudWatch Log Group ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 30

  tags = { Name = "${var.app_name}-logs" }
}

# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "app" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.app_name}-cluster" }
}

# ── Task Definition ───────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "app" {
  family                   = var.app_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024" # 1 vCPU
  memory                   = "2048" # 2 GB

  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn

  volume {
    name = "efs-data"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.app.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.app.id
        iam             = "DISABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name  = var.app_name
      image = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "DB_PATH"
          value = "/data/links.db"
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "efs-data"
          containerPath = "/data"
          readOnly      = false
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.app_name}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.container_port}/')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }

      essential = true
    }
  ])

  tags = { Name = "${var.app_name}-task" }
}

# ── ECS Service ───────────────────────────────────────────────────────────────

resource "aws_ecs_service" "app" {
  name            = "${var.app_name}-service"
  cluster         = aws_ecs_cluster.app.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1 # SQLite on NFS: one writer at a time
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.sg_ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = var.app_name
    container_port   = var.container_port
  }

  depends_on = [
    aws_efs_mount_target.private_a,
    aws_efs_mount_target.private_b,
    aws_lb_listener.http,
  ]

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = { Name = "${var.app_name}-service" }
}
