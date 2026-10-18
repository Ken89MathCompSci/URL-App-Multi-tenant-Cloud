# ── Configuration ──────────────────────────────────────────────────────────────
APP_NAME   := url-shortener
AWS_REGION ?= us-east-1
IMAGE_TAG  ?= latest

ECR_URL = $(shell cd infra && terraform output -raw ecr_repository_url 2>/dev/null)

# ── Help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "Targets:"
	@echo "  tf-init      Initialise Terraform (first time only)"
	@echo "  tf-plan      Show planned infrastructure changes"
	@echo "  tf-apply     Apply infrastructure changes"
	@echo "  docker-build Build the Docker image locally"
	@echo "  docker-push  Tag and push image to ECR"
	@echo "  deploy       Full deploy: tf-apply + docker-build + docker-push"
	@echo "  tf-destroy   Tear down all infrastructure"

# ── Terraform ──────────────────────────────────────────────────────────────────
.PHONY: tf-init tf-plan tf-apply tf-destroy

tf-init:
	cd infra && terraform init

tf-plan:
	cd infra && terraform plan -var="image_tag=$(IMAGE_TAG)"

tf-apply:
	cd infra && terraform apply -var="image_tag=$(IMAGE_TAG)" -auto-approve

tf-destroy:
	cd infra && terraform destroy -var="image_tag=$(IMAGE_TAG)"

# ── Docker / ECR ───────────────────────────────────────────────────────────────
.PHONY: docker-build ecr-login docker-push

docker-build:
	docker build -t $(APP_NAME):$(IMAGE_TAG) .

ecr-login:
	aws ecr get-login-password --region $(AWS_REGION) \
	  | docker login --username AWS --password-stdin $(ECR_URL)

docker-push: ecr-login
	docker tag $(APP_NAME):$(IMAGE_TAG) $(ECR_URL):$(IMAGE_TAG)
	docker push $(ECR_URL):$(IMAGE_TAG)

# ── Full deploy ────────────────────────────────────────────────────────────────
# First-time bootstrap: ECR must exist before the image can be pushed,
# but the task definition references the ECR URL, so we do a targeted apply first.
.PHONY: bootstrap deploy

bootstrap:
	cd infra && terraform apply -target=aws_ecr_repository.app -var="image_tag=$(IMAGE_TAG)" -auto-approve
	$(MAKE) docker-build docker-push
	cd infra && terraform apply -var="image_tag=$(IMAGE_TAG)" -auto-approve
	@echo ""
	@echo "Live at: http://$(shell cd infra && terraform output -raw alb_dns_name)"

deploy: tf-apply docker-build docker-push
	cd infra && terraform apply -var="image_tag=$(IMAGE_TAG)" -auto-approve
	@echo ""
	@echo "Live at: http://$(shell cd infra && terraform output -raw alb_dns_name)"
