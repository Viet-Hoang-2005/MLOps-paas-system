# Data AMI Ubuntu
data "aws_ami" "ubuntu_22_04" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# EC2 Master Node
resource "aws_instance" "master_node" {
  ami                    = data.aws_ami.ubuntu_22_04.id
  instance_type          = var.master_instance_type
  subnet_id              = var.public_subnet_1a_id
  vpc_security_group_ids = [var.master_sg_id]
  key_name               = var.key_name

  root_block_device {
    volume_size = var.master_volume_size
    volume_type = "gp3"
  }

  lifecycle {
    ignore_changes = [ami]
  }

  tags = { Name = "mlops-master-node" }
}

# Elastic IP cố định cho Master Node
resource "aws_eip" "master_eip" {
  domain   = "vpc"
  instance = aws_instance.master_node.id
  tags     = { Name = "mlops-master-eip" }
}

# EC2 Worker Node
resource "aws_instance" "worker_nodes" {
  count                  = var.worker_instance_count
  ami                    = data.aws_ami.ubuntu_22_04.id
  instance_type          = var.worker_instance_type
  subnet_id              = var.private_subnet_1a_id
  vpc_security_group_ids = [var.worker_sg_id]
  key_name               = var.key_name

  root_block_device {
    volume_size = var.worker_volume_size
    volume_type = "gp3"
  }
  iam_instance_profile = var.worker_profile_name
  tags                 = { Name = "mlops-worker-${count.index + 1}" }

  lifecycle {
    ignore_changes = [ami]
  }
}
