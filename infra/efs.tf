# ── Security Group: EFS ───────────────────────────────────────────────────────

resource "aws_security_group" "sg_efs" {
  name        = "${var.app_name}-sg-efs"
  description = "Allow NFS from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from ECS tasks"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-sg-efs" }
}

# ── EFS Filesystem ────────────────────────────────────────────────────────────

resource "aws_efs_file_system" "app" {
  creation_token   = "${var.app_name}-efs"
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"
  encrypted        = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = { Name = "${var.app_name}-efs" }
}

# ── Mount Targets (one per private subnet) ────────────────────────────────────

resource "aws_efs_mount_target" "private_a" {
  file_system_id  = aws_efs_file_system.app.id
  subnet_id       = aws_subnet.private_a.id
  security_groups = [aws_security_group.sg_efs.id]
}

resource "aws_efs_mount_target" "private_b" {
  file_system_id  = aws_efs_file_system.app.id
  subnet_id       = aws_subnet.private_b.id
  security_groups = [aws_security_group.sg_efs.id]
}

# ── Access Point ──────────────────────────────────────────────────────────────
# Scopes container access to /data; auto-creates the directory with correct ownership.
# UID/GID 1000 matches the appuser created in the Dockerfile.

resource "aws_efs_access_point" "app" {
  file_system_id = aws_efs_file_system.app.id

  root_directory {
    path = "/data"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "750"
    }
  }

  posix_user {
    gid = 1000
    uid = 1000
  }

  tags = { Name = "${var.app_name}-efs-ap" }
}
