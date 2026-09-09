# infra

App Runner for the Django service, RDS Postgres behind a VPC connector, ECR for the image, and
SSM Parameter Store for the two secrets. App Runner over Fargate because it is the smaller thing
to configure and explain for one container.

```
cd infra
terraform init
terraform apply
aws ecr get-login-password | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_url)
docker build -t $(terraform output -raw ecr_repository_url):latest ..
docker push $(terraform output -raw ecr_repository_url):latest
```

Migrations run from a one-off task rather than at container start:
`aws apprunner` has no exec, so run `./manage.py migrate` from a machine with the `DATABASE_URL`
parameter, or wrap it in a Lambda. Not automated here.

This module has been written and formatted but not applied. There is no live URL yet.
