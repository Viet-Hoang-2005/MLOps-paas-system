# Yêu cầu chứng chỉ SSL wildcard cho toàn bộ hệ thống
resource "aws_acm_certificate" "mlops_cert" {
  count                     = var.enable_acm_certificate ? 1 : 0
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  tags = { Name = "mlops-cert" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "mlops_cert_val" {
  count           = var.enable_acm_certificate ? 1 : 0
  certificate_arn = aws_acm_certificate.mlops_cert[0].arn
}

resource "aws_route53_zone" "karpenter_private" {
  count = var.enable_karpenter_private_dns ? 1 : 0
  name  = var.karpenter_private_zone_name

  vpc {
    vpc_id = var.vpc_id
  }

  tags = {
    Name = "mlops-k3s-private-zone"
  }
}

resource "aws_route53_record" "k3s_api_private" {
  count   = var.enable_karpenter_private_dns ? 1 : 0
  zone_id = aws_route53_zone.karpenter_private[0].zone_id
  name    = "k3s-api.${var.karpenter_private_zone_name}"
  type    = "A"
  ttl     = 60
  records = [var.master_private_ip]
}
