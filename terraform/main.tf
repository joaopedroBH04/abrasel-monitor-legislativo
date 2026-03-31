# ============================================================================
# Abrasel Monitor Legislativo - Infraestrutura AWS (Terraform)
# Conforme secao 8.1 do documento - Custo alvo: < R$ 800/mes
# ============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "abrasel-terraform-state"
    key    = "monitor-legislativo/terraform.tfstate"
    region = "sa-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# --- Variables ---
variable "aws_region" {
  default = "sa-east-1"
}

variable "environment" {
  default = "production"
}

variable "db_password" {
  sensitive = true
}

# --- S3 Buckets (Bronze + Silver) ---
resource "aws_s3_bucket" "bronze" {
  bucket = "abrasel-monitor-bronze-${var.environment}"
  tags = { Layer = "Bronze", Project = "MonitorLegislativo" }
}

resource "aws_s3_bucket" "silver" {
  bucket = "abrasel-monitor-silver-${var.environment}"
  tags = { Layer = "Silver", Project = "MonitorLegislativo" }
}

resource "aws_s3_bucket_versioning" "bronze_versioning" {
  bucket = aws_s3_bucket.bronze.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_intelligent_tiering_configuration" "bronze_tiering" {
  bucket = aws_s3_bucket.bronze.id
  name   = "bronze-tiering"
  tiering {
    access_tier = "ARCHIVE_ACCESS"
    days        = 90
  }
}

# --- RDS PostgreSQL (Gold Layer) ---
resource "aws_db_instance" "gold" {
  identifier           = "abrasel-monitor-gold"
  engine               = "postgres"
  engine_version       = "16"
  instance_class       = "db.t4g.micro"  # Custo otimizado
  allocated_storage    = 20
  max_allocated_storage = 100
  db_name              = "monitor_legislativo"
  username             = "abrasel"
  password             = var.db_password
  skip_final_snapshot  = false
  final_snapshot_identifier = "abrasel-monitor-final"
  backup_retention_period   = 7
  publicly_accessible  = false

  tags = { Layer = "Gold", Project = "MonitorLegislativo" }
}

# --- DynamoDB (Checkpoints e Idempotencia) ---
resource "aws_dynamodb_table" "checkpoints" {
  name           = "abrasel-monitor-checkpoints"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "source"
  range_key      = "checkpoint_key"

  attribute {
    name = "source"
    type = "S"
  }
  attribute {
    name = "checkpoint_key"
    type = "S"
  }

  tags = { Project = "MonitorLegislativo" }
}

# --- ECR (Container Registry) ---
resource "aws_ecr_repository" "monitor" {
  name                 = "abrasel-monitor-legislativo"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# --- ECS Cluster (Fargate) ---
resource "aws_ecs_cluster" "monitor" {
  name = "abrasel-monitor-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "incremental" {
  family                   = "abrasel-monitor-incremental"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "monitor"
    image = "${aws_ecr_repository.monitor.repository_url}:latest"
    command = ["collect", "camara", "--mode", "incremental"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/abrasel-monitor"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "incremental"
      }
    }
    environment = [
      { name = "DATABASE_URL", value = "postgresql+asyncpg://${aws_db_instance.gold.username}:${var.db_password}@${aws_db_instance.gold.endpoint}/${aws_db_instance.gold.db_name}" },
      { name = "S3_BUCKET_BRONZE", value = aws_s3_bucket.bronze.id },
      { name = "S3_BUCKET_SILVER", value = aws_s3_bucket.silver.id },
    ]
  }])
}

# --- EventBridge (Agendamento) ---
resource "aws_scheduler_schedule" "incremental_daily" {
  name       = "abrasel-monitor-incremental-daily"
  group_name = "default"

  schedule_expression = "cron(0 9 * * ? *)"  # 06h00 BRT = 09h00 UTC

  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_ecs_cluster.monitor.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.incremental.arn
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = []  # Preencher com subnets da VPC
        assign_public_ip = true
      }
    }
  }
}

resource "aws_scheduler_schedule" "agenda_daily" {
  name       = "abrasel-monitor-agenda-daily"
  group_name = "default"

  schedule_expression = "cron(0 10 * * ? *)"  # 07h00 BRT = 10h00 UTC

  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_ecs_cluster.monitor.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.incremental.arn
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = []
        assign_public_ip = true
      }
    }
  }
}

# --- IAM Roles ---
resource "aws_iam_role" "ecs_execution" {
  name = "abrasel-monitor-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "abrasel-monitor-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "ecs_task_policy" {
  name = "abrasel-monitor-task-policy"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"], Resource = ["${aws_s3_bucket.bronze.arn}/*", "${aws_s3_bucket.silver.arn}/*"] },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"], Resource = [aws_dynamodb_table.checkpoints.arn] },
      { Effect = "Allow", Action = ["ses:SendEmail", "ses:SendRawEmail"], Resource = ["*"] },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["*"] },
    ]
  })
}

resource "aws_iam_role" "scheduler" {
  name = "abrasel-monitor-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" } }]
  })
}

# --- CloudWatch ---
resource "aws_cloudwatch_log_group" "monitor" {
  name              = "/ecs/abrasel-monitor"
  retention_in_days = 30
}

resource "aws_cloudwatch_metric_alarm" "task_failure" {
  alarm_name          = "abrasel-monitor-task-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Alerta quando task do monitor falha"
  alarm_actions       = []  # Adicionar SNS topic ARN
}

# --- Outputs ---
output "bronze_bucket" { value = aws_s3_bucket.bronze.id }
output "silver_bucket" { value = aws_s3_bucket.silver.id }
output "rds_endpoint" { value = aws_db_instance.gold.endpoint }
output "ecr_repository" { value = aws_ecr_repository.monitor.repository_url }
