# App Runner in front of RDS Postgres. Secrets live in SSM Parameter Store and reach the
# service by ARN, so nothing sensitive lands in Terraform state or the task definition.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "django_secret" {
  length  = 50
  special = false
}

resource "aws_security_group" "db" {
  name   = "${var.name}-db"
  vpc_id = data.aws_vpc.default.id
}

resource "aws_security_group" "app" {
  name   = "${var.name}-app"
  vpc_id = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_subnet_group" "db" {
  name       = "${var.name}-db"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "db" {
  identifier             = var.name
  engine                 = "postgres"
  engine_version         = "17"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  db_name                = "pipeline"
  username               = "pipeline"
  password               = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  skip_final_snapshot    = true
  publicly_accessible    = false
}

resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.name}/DATABASE_URL"
  type  = "SecureString"
  value = "postgres://pipeline:${random_password.db.result}@${aws_db_instance.db.address}:5432/pipeline"
}

resource "aws_ssm_parameter" "django_secret" {
  name  = "/${var.name}/DJANGO_SECRET_KEY"
  type  = "SecureString"
  value = random_password.django_secret.result
}

resource "aws_apprunner_vpc_connector" "app" {
  vpc_connector_name = var.name
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.app.id]
}

resource "aws_apprunner_service" "app" {
  service_name = var.name

  source_configuration {
    auto_deployments_enabled = true

    authentication_configuration {
      access_role_arn = aws_iam_role.access.arn
    }

    image_repository {
      image_repository_type = "ECR"
      image_identifier      = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"

      image_configuration {
        port = "8000"
        runtime_environment_variables = {
          DJANGO_ALLOWED_HOSTS = "*"
        }
        runtime_environment_secrets = {
          DATABASE_URL      = aws_ssm_parameter.database_url.arn
          DJANGO_SECRET_KEY = aws_ssm_parameter.django_secret.arn
        }
      }
    }
  }

  instance_configuration {
    cpu               = "1024"
    memory            = "2048"
    instance_role_arn = aws_iam_role.instance.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.app.arn
    }
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/api/health/"
  }
}
