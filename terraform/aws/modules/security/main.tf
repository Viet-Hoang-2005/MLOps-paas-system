# Security Group cho Load Balancer
resource "aws_security_group" "lb_sg" {
  count       = var.enable_legacy_security_groups ? 1 : 0
  name        = "mlops-lb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "mlops-lb-sg" }
}

# Security Group cho Master Node
resource "aws_security_group" "master_sg" {
  count       = var.enable_legacy_security_groups ? 1 : 0
  name        = "mlops-master-sg"
  description = "Security group for K3s Master Node"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/16"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "mlops-master-sg" }
}

# Security Group cho Worker Node
resource "aws_security_group" "worker_sg" {
  count       = var.enable_legacy_security_groups ? 1 : 0
  name        = "mlops-worker-sg"
  description = "Security group for K3s Worker Node"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.lb_sg[0].id]
  }
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/16"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(
    { Name = "mlops-worker-sg" },
    var.enable_karpenter ? { "karpenter.sh/discovery" = var.karpenter_cluster_name } : {}
  )
}
