data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ── Task Execution Role ───────────────────────────────────────────────────────
# Used by the ECS agent: pull ECR image, write CloudWatch Logs

resource "aws_iam_role" "ecs_task_execution_role" {
  name               = "${var.app_name}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json

  tags = { Name = "${var.app_name}-ecs-execution-role" }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Task Role ─────────────────────────────────────────────────────────────────
# Assumed by the application container itself.
# No permissions needed today (SQLite via EFS, no AWS API calls).
# Add policy attachments here if the app ever needs AWS API access.

resource "aws_iam_role" "ecs_task_role" {
  name               = "${var.app_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json

  tags = { Name = "${var.app_name}-ecs-task-role" }
}
