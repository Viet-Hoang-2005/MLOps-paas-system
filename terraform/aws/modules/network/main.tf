# VPC
resource "aws_vpc" "mlops_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "mlops-vpc" }
}

# Subnet Public 1a
resource "aws_subnet" "public_1a" {
  vpc_id                  = aws_vpc.mlops_vpc.id
  cidr_block              = var.public_subnet_1a_cidr
  availability_zone       = "ap-southeast-1a"
  map_public_ip_on_launch = true
  tags                    = { Name = "mlops-subnet-public" }
}

# Subnet Public Backup 1b
resource "aws_subnet" "public_1b" {
  vpc_id                  = aws_vpc.mlops_vpc.id
  cidr_block              = var.public_subnet_1b_cidr
  availability_zone       = "ap-southeast-1b"
  map_public_ip_on_launch = true
  tags                    = { Name = "mlops-subnet-public-backup" }
}

# Subnet Private 1a
resource "aws_subnet" "private_1a" {
  vpc_id            = aws_vpc.mlops_vpc.id
  cidr_block        = var.private_subnet_1a_cidr
  availability_zone = "ap-southeast-1a"
  tags = merge(
    { Name = "mlops-subnet-private" },
    var.enable_karpenter ? { "karpenter.sh/discovery" = var.karpenter_cluster_name } : {}
  )
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.mlops_vpc.id
  tags   = { Name = "mlops-igw" }
}

# Elastic IP cho NAT Gateway
resource "aws_eip" "nat_eip" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
  tags   = { Name = "mlops-nat-eip" }
}

# NAT Gateway
resource "aws_nat_gateway" "nat_gw" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat_eip[0].id
  subnet_id     = aws_subnet.public_1a.id
  tags          = { Name = "mlops-nat-gw" }
  depends_on    = [aws_internet_gateway.igw]
}

# Route Table Public
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.mlops_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "mlops-public-rt" }
}

# Route Table Association Public 1a
resource "aws_route_table_association" "pub_1a_assoc" {
  subnet_id      = aws_subnet.public_1a.id
  route_table_id = aws_route_table.public_rt.id
}

# Route Table Association Public 1b
resource "aws_route_table_association" "pub_1b_assoc" {
  subnet_id      = aws_subnet.public_1b.id
  route_table_id = aws_route_table.public_rt.id
}

# Route Table Private
resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.mlops_vpc.id

  dynamic "route" {
    for_each = var.enable_nat_gateway ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.nat_gw[0].id
    }
  }

  tags = { Name = "mlops-private-rt" }
}

# Route Table Association Private 1a
resource "aws_route_table_association" "priv_1a_assoc" {
  subnet_id      = aws_subnet.private_1a.id
  route_table_id = aws_route_table.private_rt.id
}
