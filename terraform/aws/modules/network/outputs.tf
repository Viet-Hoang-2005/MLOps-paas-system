output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.mlops_vpc.id
}

output "public_subnet_1a_id" {
  description = "The ID of the public subnet 1a"
  value       = aws_subnet.public_1a.id
}

output "public_subnet_1b_id" {
  description = "The ID of the public subnet 1b"
  value       = aws_subnet.public_1b.id
}

output "private_subnet_1a_id" {
  description = "The ID of the private subnet 1a"
  value       = aws_subnet.private_1a.id
}
